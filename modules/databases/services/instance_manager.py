import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
import secrets
import string

from module_sdk import (
    AsyncSession, text, HTTPException
)

# Import get_db_context for background tasks
from database import get_db_context

# Import table constants from parent module
from .. import (
    INSTANCES_TABLE,
    SNAPSHOTS_TABLE,
    BACKUPS_TABLE,
    TABLE_PREFIX,
    MODULE_ID
)

# Import services
from .adapters import get_adapter
from .container_orchestrator import ContainerOrchestrator
from .credential_manager import CredentialManager
from .volume_service import VolumeService

logger = logging.getLogger("uvicorn.error")


class InstanceManager:
    """Core instance lifecycle manager for database instances."""
    
    @staticmethod
    def _generate_container_name(engine_type: str, instance_name: str) -> str:
        """Generate a unique container name."""
        # Sanitize instance name for container naming
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in instance_name)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"db_{engine_type}_{safe_name}_{timestamp}"
    
    @staticmethod
    def _generate_password(length: int = 32) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    async def _create_instance_background(
        instance_id: int,
        engine_type: str,
        container_name: str,
        database_name: str,
        username: str,
        password: str,
        sku: str,
        memory_mb: int,
        cpu: int,
        storage_gb: int,
        external_access: bool,
        tls_enabled: bool,
        tls_cert: Optional[str],
        tls_key: Optional[str],
        vnet_name: Optional[str]
    ):
        """Background task to create the container and initialize the database."""
        async with get_db_context() as db:
            try:
                logger.info(f"Creating container for instance {instance_id}")
                
                # Get adapter for the engine type
                adapter = get_adapter(engine_type)
                
                # Create data volume
                volume_name = f"{container_name}_data"
                await VolumeService.create_volume(volume_name, storage_gb)
                
                # Prepare container configuration
                container_config = {
                    "image": adapter.get_container_image(),
                    "environment": adapter.get_environment_vars(
                        database_name, username, password
                    ),
                    "memory_mb": memory_mb,
                    "cpu": cpu,
                    "volumes": {
                        volume_name: adapter.get_data_mount_path()
                    },
                    "ports": adapter.get_port_mappings(),
                    "external_access": external_access,
                    "tls_enabled": tls_enabled,
                    "tls_cert": tls_cert,
                    "tls_key": tls_key,
                    "vnet_name": vnet_name
                }
                
                # Create and start container
                orchestrator = ContainerOrchestrator()
                container_info = await orchestrator.create_container(
                    container_name, container_config
                )
                
                # Update instance status to running
                await db.execute(
                    text(f'''
                        UPDATE "{INSTANCES_TABLE}"
                        SET status = :status,
                            container_id = :container_id,
                            internal_host = :internal_host,
                            internal_port = :internal_port,
                            external_host = :external_host,
                            external_port = :external_port,
                            volume_name = :volume_name,
                            updated_at = :updated_at
                        WHERE id = :instance_id
                    '''),
                    {
                        "status": "running",
                        "container_id": container_info.get("container_id"),
                        "internal_host": container_info.get("internal_host"),
                        "internal_port": container_info.get("internal_port"),
                        "external_host": container_info.get("external_host"),
                        "external_port": container_info.get("external_port"),
                        "volume_name": volume_name,
                        "updated_at": datetime.utcnow().isoformat(),
                        "instance_id": instance_id
                    }
                )
                await db.commit()
                
                logger.info(f"Instance {instance_id} created successfully")
                
            except Exception as e:
                logger.error(f"Failed to create instance {instance_id}: {e}")
                # Update status to failed
                await db.execute(
                    text(f'''
                        UPDATE "{INSTANCES_TABLE}"
                        SET status = :status,
                            error_message = :error_message,
                            updated_at = :updated_at
                        WHERE id = :instance_id
                    '''),
                    {
                        "status": "failed",
                        "error_message": str(e),
                        "updated_at": datetime.utcnow().isoformat(),
                        "instance_id": instance_id
                    }
                )
                await db.commit()
    
    @staticmethod
    async def create_instance(
        db: AsyncSession,
        engine_type: str,
        name: str,
        database_name: str,
        sku: str,
        memory_mb: int,
        cpu: int,
        storage_gb: int,
        external_access: bool = False,
        tls_enabled: bool = False,
        tls_cert: Optional[str] = None,
        tls_key: Optional[str] = None,
        vnet_name: Optional[str] = None
    ) -> dict:
        """Create a new database instance."""
        
        # Validate engine type
        try:
            get_adapter(engine_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Generate container name and credentials
        container_name = InstanceManager._generate_container_name(engine_type, name)
        username = "admin"
        password = InstanceManager._generate_password()
        
        # Insert instance record
        result = await db.execute(
            text(f'''
                INSERT INTO "{INSTANCES_TABLE}" (
                    name, engine_type, database_name, container_name,
                    sku, memory_mb, cpu, storage_gb,
                    external_access, tls_enabled,
                    status, created_at, updated_at
                )
                VALUES (
                    :name, :engine_type, :database_name, :container_name,
                    :sku, :memory_mb, :cpu, :storage_gb,
                    :external_access, :tls_enabled,
                    :status, :created_at, :updated_at
                )
                RETURNING id
            '''),
            {
                "name": name,
                "engine_type": engine_type,
                "database_name": database_name,
                "container_name": container_name,
                "sku": sku,
                "memory_mb": memory_mb,
                "cpu": cpu,
                "storage_gb": storage_gb,
                "external_access": external_access,
                "tls_enabled": tls_enabled,
                "status": "creating",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        )
        await db.commit()
        
        instance_id = result.scalar_one()
        
        # Store credentials
        await CredentialManager.store_credentials(
            db, instance_id, username, password
        )
        await db.commit()
        
        # Start background task for container creation
        asyncio.create_task(
            InstanceManager._create_instance_background(
                instance_id, engine_type, container_name, database_name,
                username, password, sku, memory_mb, cpu, storage_gb,
                external_access, tls_enabled, tls_cert, tls_key, vnet_name
            )
        )
        
        # Return instance info immediately
        return {
            "id": instance_id,
            "name": name,
            "engine_type": engine_type,
            "database_name": database_name,
            "container_name": container_name,
            "status": "creating",
            "created_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def start_instance(db: AsyncSession, instance_id: int) -> dict:
        """Start a stopped database instance."""
        
        # Look up instance
        result = await db.execute(
            text(f'SELECT container_name, status FROM "{INSTANCES_TABLE}" WHERE id = :id'),
            {"id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        container_name = row[0]
        current_status = row[1]
        
        if current_status == "running":
            raise HTTPException(status_code=400, detail="Instance is already running")
        
        # Start container
        orchestrator = ContainerOrchestrator()
        await orchestrator.start_container(container_name)
        
        # Update status
        await db.execute(
            text(f'''
                UPDATE "{INSTANCES_TABLE}"
                SET status = :status, updated_at = :updated_at
                WHERE id = :instance_id
            '''),
            {
                "status": "running",
                "updated_at": datetime.utcnow().isoformat(),
                "instance_id": instance_id
            }
        )
        await db.commit()
        
        return {"id": instance_id, "status": "running"}
    
    @staticmethod
    async def stop_instance(db: AsyncSession, instance_id: int) -> dict:
        """Stop a running database instance."""
        
        # Look up instance
        result = await db.execute(
            text(f'SELECT container_name, status FROM "{INSTANCES_TABLE}" WHERE id = :id'),
            {"id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        container_name = row[0]
        current_status = row[1]
        
        if current_status == "stopped":
            raise HTTPException(status_code=400, detail="Instance is already stopped")
        
        # Stop container
        orchestrator = ContainerOrchestrator()
        await orchestrator.stop_container(container_name)
        
        # Update status
        await db.execute(
            text(f'''
                UPDATE "{INSTANCES_TABLE}"
                SET status = :status, updated_at = :updated_at
                WHERE id = :instance_id
            '''),
            {
                "status": "stopped",
                "updated_at": datetime.utcnow().isoformat(),
                "instance_id": instance_id
            }
        )
        await db.commit()
        
        return {"id": instance_id, "status": "stopped"}
    
    @staticmethod
    async def restart_instance(db: AsyncSession, instance_id: int) -> dict:
        """Restart a database instance."""
        
        # Look up instance
        result = await db.execute(
            text(f'SELECT container_name FROM "{INSTANCES_TABLE}" WHERE id = :id'),
            {"id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        container_name = row[0]
        
        # Restart container
        orchestrator = ContainerOrchestrator()
        await orchestrator.restart_container(container_name)
        
        # Update timestamp
        await db.execute(
            text(f'''
                UPDATE "{INSTANCES_TABLE}"
                SET status = :status, updated_at = :updated_at
                WHERE id = :instance_id
            '''),
            {
                "status": "running",
                "updated_at": datetime.utcnow().isoformat(),
                "instance_id": instance_id
            }
        )
        await db.commit()
        
        return {"id": instance_id, "status": "running"}
    
    @staticmethod
    async def destroy_instance(db: AsyncSession, instance_id: int) -> dict:
        """Destroy a database instance and cleanup all resources."""
        
        # Look up instance
        result = await db.execute(
            text(f'''
                SELECT container_name, volume_name, vnet_ip
                FROM "{INSTANCES_TABLE}"
                WHERE id = :id
            '''),
            {"id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        container_name = row[0]
        volume_name = row[1]
        vnet_ip = row[2]
        
        orchestrator = ContainerOrchestrator()
        
        # Stop and remove container
        try:
            await orchestrator.stop_container(container_name)
        except Exception as e:
            logger.warning(f"Failed to stop container {container_name}: {e}")
        
        try:
            await orchestrator.remove_container(container_name)
        except Exception as e:
            logger.warning(f"Failed to remove container {container_name}: {e}")
        
        # Remove volume
        if volume_name:
            try:
                await VolumeService.delete_volume(volume_name)
            except Exception as e:
                logger.warning(f"Failed to remove volume {volume_name}: {e}")
        
        # Release VNet IP if allocated
        if vnet_ip:
            try:
                from module_sdk import release_vnet_ip
                await release_vnet_ip(vnet_ip)
            except Exception as e:
                logger.warning(f"Failed to release VNet IP {vnet_ip}: {e}")
        
        # Delete credentials
        await CredentialManager.delete_credentials(db, instance_id)
        
        # Delete instance from database
        await db.execute(
            text(f'DELETE FROM "{INSTANCES_TABLE}" WHERE id = :id'),
            {"id": instance_id}
        )
        await db.commit()
        
        return {"id": instance_id, "status": "destroyed"}
    
    @staticmethod
    async def get_instance(db: AsyncSession, instance_id: int) -> dict:
        """Get full instance information with container status."""
        
        # Query instance
        result = await db.execute(
            text(f'SELECT * FROM "{INSTANCES_TABLE}" WHERE id = :id'),
            {"id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        # Convert to dict
        columns = result.keys()
        instance = dict(zip(columns, row))
        
        # Get container status
        container_name = instance.get("container_name")
        if container_name:
            orchestrator = ContainerOrchestrator()
            try:
                container_status = await orchestrator.get_container_status(container_name)
                instance["container_status"] = container_status
            except Exception as e:
                logger.warning(f"Failed to get container status: {e}")
                instance["container_status"] = {"state": "unknown"}
        
        # Get credentials (if user has permission)
        try:
            credentials = await CredentialManager.get_credentials(db, instance_id)
            instance["username"] = credentials.get("username")
            instance["password"] = credentials.get("password")
        except Exception:
            pass
        
        return instance
    
    @staticmethod
    async def list_instances(
        db: AsyncSession,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[dict]:
        """List all database instances with optional filters."""
        
        query = f'SELECT * FROM "{INSTANCES_TABLE}"'
        params = {}
        
        if filters:
            conditions = []
            if "engine_type" in filters:
                conditions.append("engine_type = :engine_type")
                params["engine_type"] = filters["engine_type"]
            if "status" in filters:
                conditions.append("status = :status")
                params["status"] = filters["status"]
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY created_at DESC"
        
        result = await db.execute(text(query), params)
        rows = result.fetchall()
        columns = result.keys()
        
        instances = []
        orchestrator = ContainerOrchestrator()
        
        for row in rows:
            instance = dict(zip(columns, row))
            
            # Merge container status
            container_name = instance.get("container_name")
            if container_name:
                try:
                    container_status = await orchestrator.get_container_status(container_name)
                    instance["container_status"] = container_status
                except Exception:
                    instance["container_status"] = {"state": "unknown"}
            
            instances.append(instance)
        
        return instances
    
    @staticmethod
    async def get_instance_status(db: AsyncSession, instance_id: int) -> dict:
        """Get combined database and container status."""
        
        # Query instance
        result = await db.execute(
            text(f'SELECT status, container_name FROM "{INSTANCES_TABLE}" WHERE id = :id'),
            {"id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        db_status = row[0]
        container_name = row[1]
        
        status_info = {
            "instance_id": instance_id,
            "db_status": db_status,
            "container_status": None
        }
        
        # Get container status
        if container_name:
            orchestrator = ContainerOrchestrator()
            try:
                container_status = await orchestrator.get_container_status(container_name)
                status_info["container_status"] = container_status
            except Exception as e:
                logger.warning(f"Failed to get container status: {e}")
                status_info["container_status"] = {"state": "unknown", "error": str(e)}
        
        return status_info
