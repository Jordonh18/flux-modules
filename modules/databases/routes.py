"""
Databases Module - API Routes

Database management endpoints.
The router is automatically mounted at /api/modules/databases/
"""

from module_sdk import (
    ModuleRouter,
    get_db,
    AsyncSession,
    text,
    require_permission,
    Depends,
    HTTPException,
    BaseModel,
    Optional,
    List,
    Dict,
    Any,
    # VNet hooks
    allocate_vnet_ip,
    release_vnet_ip,
    get_module_allocations,
    list_available_vnets,
)
from database import get_db_context
import secrets
import asyncio
import logging
import os
import time as _time
import subprocess
import json

from . import (
    INSTANCES_TABLE,
    SNAPSHOTS_TABLE,
    BACKUPS_TABLE,
    METRICS_TABLE,
    HEALTH_TABLE,
    CREDENTIALS_TABLE,
    USERS_TABLE,
    DATABASES_TABLE,
)
from .services import (
    get_adapter,
    list_engines,
    ContainerOrchestrator,
    BackupService,
    MetricsCollector,
    HealthMonitor,
    CredentialManager,
    DatabaseOperations,
    VolumeService,
    InstanceManager,
)

logger = logging.getLogger("uvicorn.error")
router = ModuleRouter("databases")


# ============================================================================
# SKU Definitions (Azure-style tiers)
# Series determine container scheduling behavior via Podman flags:
#   B-series (Burstable): cpu-shares=512 — low priority, yields under contention
#   D-series (General Purpose): cpu-shares=1024 — standard balanced performance
#   E-series (Memory Optimized): swappiness=0, oom-score-adj=-500 — keeps data in RAM, OOM protected
#   F-series (Compute Optimized): cpu-shares=2048, memory-swap=memory — high CPU priority, strict no-swap
# ============================================================================

SKU_DEFINITIONS = {
    # B-series: Burstable (Low CPU priority, deprioritized under host contention)
    "b1": {"memory_mb": 1024, "cpus": 0.5, "storage_gb": 10},
    "b2": {"memory_mb": 2048, "cpus": 1.0, "storage_gb": 20},
    "b4": {"memory_mb": 4096, "cpus": 2.0, "storage_gb": 40},
    
    # D-series: General Purpose (Standard CPU priority, balanced defaults)
    "d2": {"memory_mb": 4096, "cpus": 2.0, "storage_gb": 50},
    "d4": {"memory_mb": 8192, "cpus": 4.0, "storage_gb": 100},
    "d8": {"memory_mb": 16384, "cpus": 8.0, "storage_gb": 200},
    "d16": {"memory_mb": 32768, "cpus": 16.0, "storage_gb": 500},
    "d32": {"memory_mb": 65536, "cpus": 32.0, "storage_gb": 1024},
    "d64": {"memory_mb": 131072, "cpus": 64.0, "storage_gb": 2048},
    
    # E-series: Memory Optimized (No swap, OOM kill protection, data stays in RAM)
    "e2": {"memory_mb": 8192, "cpus": 2.0, "storage_gb": 50},
    "e4": {"memory_mb": 16384, "cpus": 4.0, "storage_gb": 100},
    "e8": {"memory_mb": 32768, "cpus": 8.0, "storage_gb": 200},
    "e16": {"memory_mb": 65536, "cpus": 16.0, "storage_gb": 500},
    "e32": {"memory_mb": 131072, "cpus": 32.0, "storage_gb": 1024},
    "e64": {"memory_mb": 262144, "cpus": 64.0, "storage_gb": 2048},
    
    # F-series: Compute Optimized (High CPU priority, strict no-swap)
    "f2": {"memory_mb": 2048, "cpus": 2.0, "storage_gb": 30},
    "f4": {"memory_mb": 4096, "cpus": 4.0, "storage_gb": 60},
    "f8": {"memory_mb": 8192, "cpus": 8.0, "storage_gb": 120},
    "f16": {"memory_mb": 16384, "cpus": 16.0, "storage_gb": 240},
    "f32": {"memory_mb": 32768, "cpus": 32.0, "storage_gb": 480},
    "f64": {"memory_mb": 65536, "cpus": 64.0, "storage_gb": 960},
    
    # Custom: User-defined resources
    "custom": None,  # Uses provided values
}


# ============================================================================
# Pydantic Models
# ============================================================================

class CreateDatabaseRequest(BaseModel):
    """Request to create a new database instance"""
    engine: str
    name: Optional[str] = None
    database_name: str = "app"
    sku: str = "d2"
    memory_limit_mb: Optional[int] = None
    cpu_limit: Optional[float] = None
    storage_limit_gb: Optional[int] = None
    external_access: bool = False
    tls_enabled: bool = False
    tls_cert: Optional[str] = None
    tls_key: Optional[str] = None
    vnet_name: Optional[str] = None


class RotateCredentialsRequest(BaseModel):
    """Request to rotate instance credentials"""
    pass  # Empty, just triggers rotation


class CreateUserRequest(BaseModel):
    """Request to create a user within an instance"""
    username: str
    password: Optional[str] = None  # Auto-generated if not provided
    permissions: Optional[List[str]] = None


class CreateInnerDatabaseRequest(BaseModel):
    """Request to create a database within an instance"""
    name: str


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_mem_value(s: str) -> float:
    """Parse a memory string like '123.4MiB' or '1.2GiB' into MB."""
    s = s.strip()
    try:
        if s.lower().endswith("gib"):
            return float(s[:-3]) * 1024
        elif s.lower().endswith("gb"):
            return float(s[:-2]) * 1024
        elif s.lower().endswith("mib"):
            return float(s[:-3])
        elif s.lower().endswith("mb"):
            return float(s[:-2])
        elif s.lower().endswith("kib"):
            return float(s[:-3]) / 1024
        elif s.lower().endswith("kb"):
            return float(s[:-2]) / 1024
        elif s.lower().endswith("b"):
            return float(s[:-1]) / (1024 * 1024)
        return float(s)
    except ValueError:
        return 0.0


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/status")
async def get_status():
    """Get databases module status."""
    try:
        result = subprocess.run(
            ["podman", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        podman_installed = result.returncode == 0
        version = result.stdout.strip() if podman_installed else None
    except Exception:
        podman_installed = False
        version = None
    
    return {
        "status": "ok",
        "message": "Databases module is running",
        "podman": {
            "installed": podman_installed,
            "version": version
        }
    }


@router.get("/requirements")
async def check_requirements():
    """Check system requirements for running database containers."""
    try:
        # Check Podman installation
        podman_result = subprocess.run(
            ["podman", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        podman_ok = podman_result.returncode == 0
        
        # Check available disk space
        stat_result = subprocess.run(
            ["df", "-BG", "/"],
            capture_output=True,
            text=True,
            timeout=5
        )
        disk_available_gb = 0
        if stat_result.returncode == 0:
            lines = stat_result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) > 3:
                    disk_available_gb = int(parts[3].replace('G', ''))
        
        return {
            "podman_installed": podman_ok,
            "podman_version": podman_result.stdout.strip() if podman_ok else None,
            "disk_available_gb": disk_available_gb,
            "requirements_met": podman_ok and disk_available_gb >= 10
        }
    except Exception as e:
        logger.error(f"Error checking requirements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-info")
async def get_system_info():
    """Get host system information (CPU, memory)."""
    try:
        # CPU info
        cpu_count = os.cpu_count() or 1
        
        # Memory info
        mem_info = {}
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("MemTotal:"):
                        mem_info["total_mb"] = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        mem_info["available_mb"] = int(line.split()[1]) // 1024
        except Exception:
            pass
        
        return {
            "cpu_count": cpu_count,
            "memory": mem_info
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/podman/status")
async def get_podman_status():
    """Check Podman installation status."""
    try:
        result = subprocess.run(
            ["podman", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return {
                "installed": True,
                "version": result.stdout.strip(),
                "message": "Podman is installed and ready"
            }
        else:
            return {
                "installed": False,
                "version": None,
                "message": "Podman is not installed"
            }
    except FileNotFoundError:
        return {
            "installed": False,
            "version": None,
            "message": "Podman is not installed"
        }
    except Exception as e:
        logger.error(f"Error checking Podman status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/podman/install", dependencies=[Depends(require_permission("databases:write"))])
async def install_podman():
    """Install Podman on the host system."""
    try:
        # This is a placeholder - actual installation depends on the host OS
        # For Debian/Ubuntu:
        result = subprocess.run(
            ["sudo", "apt-get", "install", "-y", "podman"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            return {
                "success": True,
                "message": "Podman installed successfully"
            }
        else:
            return {
                "success": False,
                "message": f"Installation failed: {result.stderr}"
            }
    except Exception as e:
        logger.error(f"Error installing Podman: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/engines")
async def get_engines():
    """List all supported database engines from the adapter registry."""
    engines = list_engines()
    return {
        "engines": engines,
        "count": len(engines)
    }


@router.get("/skus")
async def get_skus():
    """List all available SKU definitions."""
    return {
        "skus": SKU_DEFINITIONS,
        "count": len([k for k in SKU_DEFINITIONS.keys() if k != "custom"])
    }


@router.get("/databases", dependencies=[Depends(require_permission("databases:read"))])
async def list_databases(db: AsyncSession = Depends(get_db)):
    """List all database instances."""
    try:
        result = await db.execute(text(f'''
            SELECT id, container_id, container_name, database_type, host, port,
                   database_name, username, password, status, error_message, created_at,
                   sku, memory_limit_mb, cpu_limit, storage_limit_gb, external_access, tls_enabled
            FROM "{INSTANCES_TABLE}"
            ORDER BY created_at DESC
        '''))
        rows = result.fetchall()
        
        databases = []
        for row in rows:
            databases.append({
                "id": row[0],
                "container_id": row[1],
                "container_name": row[2],
                "database_type": row[3],
                "host": row[4],
                "port": row[5],
                "database_name": row[6],
                "username": row[7],
                "password": row[8],
                "status": row[9],
                "error_message": row[10],
                "created_at": row[11],
                "sku": row[12],
                "memory_limit_mb": row[13],
                "cpu_limit": row[14],
                "storage_limit_gb": row[15],
                "external_access": row[16],
                "tls_enabled": row[17]
            })
        
        return {"databases": databases, "count": len(databases)}
    except Exception as e:
        logger.error(f"Error listing databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases", dependencies=[Depends(require_permission("databases:write"))])
async def create_database(request: CreateDatabaseRequest, db: AsyncSession = Depends(get_db)):
    """Create a new database instance."""
    try:
        # Validate engine
        try:
            adapter = get_adapter(request.engine)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Validate SKU
        if request.sku not in SKU_DEFINITIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid SKU tier: {request.sku}. Must be one of: {', '.join(SKU_DEFINITIONS.keys())}"
            )
        
        sku_config = SKU_DEFINITIONS[request.sku]
        
        # Determine resource limits
        if request.sku == "custom":
            if not request.memory_limit_mb or not request.cpu_limit or not request.storage_limit_gb:
                raise HTTPException(
                    status_code=400,
                    detail="Custom SKU requires memory_limit_mb, cpu_limit, and storage_limit_gb"
                )
            memory_mb = request.memory_limit_mb
            cpu_limit = request.cpu_limit
            storage_gb = request.storage_limit_gb
        else:
            memory_mb = sku_config["memory_mb"]
            cpu_limit = sku_config["cpus"]
            storage_gb = sku_config["storage_gb"]
        
        # Generate credentials
        cred_mgr = CredentialManager()
        username = cred_mgr.generate_username()
        password = cred_mgr.generate_password()
        
        # Generate container name
        if request.name:
            container_name = f"db-{request.engine}-{request.name}"
        else:
            container_name = f"db-{request.engine}-{secrets.token_hex(4)}"
        
        # Insert initial record
        result = await db.execute(text(f'''
            INSERT INTO "{INSTANCES_TABLE}" (
                container_id, container_name, database_type, host, port,
                database_name, username, password, status, created_at,
                sku, memory_limit_mb, cpu_limit, storage_limit_gb,
                external_access, tls_enabled
            )
            VALUES (
                :container_id, :container_name, :database_type, :host, :port,
                :database_name, :username, :password, :status, :created_at,
                :sku, :memory_limit_mb, :cpu_limit, :storage_limit_gb,
                :external_access, :tls_enabled
            )
            RETURNING id
        '''), {
            "container_id": "",
            "container_name": container_name,
            "database_type": request.engine,
            "host": "localhost",
            "port": adapter.default_port,
            "database_name": request.database_name,
            "username": username,
            "password": password,
            "status": "creating",
            "created_at": int(_time.time()),
            "sku": request.sku,
            "memory_limit_mb": memory_mb,
            "cpu_limit": cpu_limit,
            "storage_limit_gb": storage_gb,
            "external_access": request.external_access,
            "tls_enabled": request.tls_enabled
        })
        instance_id = result.fetchone()[0]
        await db.commit()
        
        # Launch background task to create container
        async def create_container_task():
            async with get_db_context() as task_db:
                try:
                    orchestrator = ContainerOrchestrator()
                    
                    # Create container
                    container_id = await orchestrator.create_container(
                        engine=request.engine,
                        container_name=container_name,
                        username=username,
                        password=password,
                        database_name=request.database_name,
                        memory_mb=memory_mb,
                        cpu_limit=cpu_limit,
                        storage_gb=storage_gb,
                        port=adapter.default_port,
                        external_access=request.external_access,
                        tls_enabled=request.tls_enabled,
                        tls_cert=request.tls_cert,
                        tls_key=request.tls_key,
                        vnet_name=request.vnet_name
                    )
                    
                    # Start container
                    await orchestrator.start_container(container_name)
                    
                    # Store credentials
                    await cred_mgr.store_credentials(
                        instance_id=instance_id,
                        username=username,
                        password=password,
                        db=task_db
                    )
                    
                    # Update status
                    await task_db.execute(text(f'''
                        UPDATE "{INSTANCES_TABLE}"
                        SET container_id = :container_id, status = :status
                        WHERE id = :id
                    '''), {
                        "container_id": container_id,
                        "status": "running",
                        "id": instance_id
                    })
                    await task_db.commit()
                    
                except Exception as e:
                    logger.error(f"Error creating container: {e}")
                    await task_db.execute(text(f'''
                        UPDATE "{INSTANCES_TABLE}"
                        SET status = :status, error_message = :error_message
                        WHERE id = :id
                    '''), {
                        "status": "error",
                        "error_message": str(e),
                        "id": instance_id
                    })
                    await task_db.commit()
        
        asyncio.create_task(create_container_task())
        
        return {
            "id": instance_id,
            "container_name": container_name,
            "status": "creating",
            "message": "Database instance is being created"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/start", dependencies=[Depends(require_permission("databases:write"))])
async def start_database(database_id: int, db: AsyncSession = Depends(get_db)):
    """Start a database instance."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, status
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Start container
        orchestrator = ContainerOrchestrator()
        await orchestrator.start_container(container_name)
        
        # Update status
        await db.execute(text(f'''
            UPDATE "{INSTANCES_TABLE}"
            SET status = :status
            WHERE id = :id
        '''), {"status": "running", "id": database_id})
        await db.commit()
        
        return {"message": "Database started successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/stop", dependencies=[Depends(require_permission("databases:write"))])
async def stop_database(database_id: int, db: AsyncSession = Depends(get_db)):
    """Stop a database instance."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Stop container
        orchestrator = ContainerOrchestrator()
        await orchestrator.stop_container(container_name)
        
        # Update status
        await db.execute(text(f'''
            UPDATE "{INSTANCES_TABLE}"
            SET status = :status
            WHERE id = :id
        '''), {"status": "stopped", "id": database_id})
        await db.commit()
        
        return {"message": "Database stopped successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/restart", dependencies=[Depends(require_permission("databases:write"))])
async def restart_database(database_id: int, db: AsyncSession = Depends(get_db)):
    """Restart a database instance."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Restart container
        orchestrator = ContainerOrchestrator()
        await orchestrator.restart_container(container_name)
        
        # Update status
        await db.execute(text(f'''
            UPDATE "{INSTANCES_TABLE}"
            SET status = :status
            WHERE id = :id
        '''), {"status": "running", "id": database_id})
        await db.commit()
        
        return {"message": "Database restarted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/databases/{database_id}", dependencies=[Depends(require_permission("databases:write"))])
async def delete_database(database_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a database instance."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, container_id
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Remove container
        orchestrator = ContainerOrchestrator()
        await orchestrator.remove_container(container_name)
        
        # Delete from database
        await db.execute(text(f'''
            DELETE FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        await db.commit()
        
        return {"message": "Database deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/logs", dependencies=[Depends(require_permission("databases:read"))])
async def get_database_logs(database_id: int, tail: int = 100, db: AsyncSession = Depends(get_db)):
    """Get database container logs."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Get logs
        orchestrator = ContainerOrchestrator()
        logs = await orchestrator.get_logs(container_name, tail=tail)
        
        return {"logs": logs}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/metrics", dependencies=[Depends(require_permission("databases:read"))])
async def get_database_metrics(database_id: int, hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Get database metrics history."""
    try:
        collector = MetricsCollector()
        metrics = await collector.get_metrics_history(database_id, hours=hours, db=db)
        
        return {
            "instance_id": database_id,
            "hours": hours,
            "metrics": metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/stats", dependencies=[Depends(require_permission("databases:read"))])
async def get_database_stats(database_id: int, db: AsyncSession = Depends(get_db)):
    """Get current database container stats."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Get stats
        orchestrator = ContainerOrchestrator()
        stats_output = await orchestrator.get_stats(container_name)
        
        # Parse stats output
        lines = stats_output.strip().split('\n')
        if len(lines) < 2:
            raise HTTPException(status_code=500, detail="Invalid stats output")
        
        # Parse the data line (skip header)
        parts = lines[1].split()
        if len(parts) < 8:
            raise HTTPException(status_code=500, detail="Invalid stats format")
        
        # Extract memory usage
        mem_usage = parts[2]
        mem_parts = mem_usage.split('/')
        mem_used_mb = _parse_mem_value(mem_parts[0].strip())
        mem_limit_mb = _parse_mem_value(mem_parts[1].strip()) if len(mem_parts) > 1 else 0
        
        # Extract CPU percentage
        cpu_percent = parts[1].strip('%')
        
        return {
            "container_name": container_name,
            "cpu_percent": float(cpu_percent) if cpu_percent else 0.0,
            "memory_used_mb": mem_used_mb,
            "memory_limit_mb": mem_limit_mb,
            "memory_percent": (mem_used_mb / mem_limit_mb * 100) if mem_limit_mb > 0 else 0.0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/inspect", dependencies=[Depends(require_permission("databases:read"))])
async def inspect_database(database_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed database container inspection."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        
        # Inspect container
        orchestrator = ContainerOrchestrator()
        inspect_output = await orchestrator.inspect(container_name)
        
        # Parse JSON output
        try:
            inspect_data = json.loads(inspect_output)
            if isinstance(inspect_data, list) and len(inspect_data) > 0:
                inspect_data = inspect_data[0]
        except json.JSONDecodeError:
            inspect_data = {"raw": inspect_output}
        
        return inspect_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inspecting container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/snapshot", dependencies=[Depends(require_permission("databases:write"))])
async def create_snapshot(database_id: int, db: AsyncSession = Depends(get_db)):
    """Create a backup/snapshot of the database."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        
        # Create backup
        backup_svc = BackupService()
        backup_id = await backup_svc.create_backup(
            instance_id=database_id,
            container_name=container_name,
            engine=database_type,
            db=db
        )
        
        return {
            "snapshot_id": backup_id,
            "message": "Snapshot created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/snapshots", dependencies=[Depends(require_permission("databases:read"))])
async def list_snapshots(database_id: int, db: AsyncSession = Depends(get_db)):
    """List all snapshots for a database instance."""
    try:
        backup_svc = BackupService()
        snapshots = await backup_svc.list_backups(instance_id=database_id, db=db)
        
        return {
            "instance_id": database_id,
            "snapshots": snapshots,
            "count": len(snapshots)
        }
        
    except Exception as e:
        logger.error(f"Error listing snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/restore/{snapshot_id}", dependencies=[Depends(require_permission("databases:write"))])
async def restore_snapshot(database_id: int, snapshot_id: int, db: AsyncSession = Depends(get_db)):
    """Restore a database from a snapshot."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        
        # Restore backup
        backup_svc = BackupService()
        await backup_svc.restore_backup(
            backup_id=snapshot_id,
            container_name=container_name,
            engine=database_type,
            db=db
        )
        
        return {"message": "Snapshot restored successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/databases/{database_id}/snapshots/{snapshot_id}", dependencies=[Depends(require_permission("databases:write"))])
async def delete_snapshot(database_id: int, snapshot_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a snapshot."""
    try:
        backup_svc = BackupService()
        await backup_svc.delete_backup(backup_id=snapshot_id, db=db)
        
        return {"message": "Snapshot deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/export", dependencies=[Depends(require_permission("databases:read"))])
async def export_database(database_id: int, db: AsyncSession = Depends(get_db)):
    """Export database as a downloadable archive."""
    # This is a placeholder - implementation would depend on specific requirements
    raise HTTPException(status_code=501, detail="Export functionality not yet implemented")


@router.get("/databases/{database_id}/tables", dependencies=[Depends(require_permission("databases:read"))])
async def list_tables(database_id: int, db: AsyncSession = Depends(get_db)):
    """List tables in the database (for SQL databases)."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type, database_name, username, password
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        database_name = row[2]
        username = row[3]
        password = row[4]
        
        # Get adapter
        adapter = get_adapter(database_type)
        
        if not adapter.supports_databases:
            raise HTTPException(status_code=400, detail=f"{database_type} does not support table listing")
        
        # Use DatabaseOperations to list tables (this would need to be implemented)
        # For now, return placeholder
        raise HTTPException(status_code=501, detail="Table listing not yet implemented")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/tables/{table_name}/schema", dependencies=[Depends(require_permission("databases:read"))])
async def get_table_schema(database_id: int, table_name: str, db: AsyncSession = Depends(get_db)):
    """Get schema for a specific table."""
    raise HTTPException(status_code=501, detail="Table schema retrieval not yet implemented")


@router.get("/databases/{database_id}/tables/{table_name}/data", dependencies=[Depends(require_permission("databases:read"))])
async def get_table_data(database_id: int, table_name: str, limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """Get data from a specific table."""
    raise HTTPException(status_code=501, detail="Table data retrieval not yet implemented")


@router.get("/databases/{database_id}/health", dependencies=[Depends(require_permission("databases:read"))])
async def get_database_health(database_id: int, db: AsyncSession = Depends(get_db)):
    """Get current health status of the database."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        
        # Check health
        health_monitor = HealthMonitor()
        health_status = await health_monitor.check_health(
            instance_id=database_id,
            container_name=container_name,
            engine=database_type,
            db=db
        )
        
        return health_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/credentials/rotate", dependencies=[Depends(require_permission("databases:write"))])
async def rotate_credentials(database_id: int, db: AsyncSession = Depends(get_db)):
    """Rotate database credentials."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type, username
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        old_username = row[2]
        
        # Rotate password
        cred_mgr = CredentialManager()
        new_password = await cred_mgr.rotate_password(
            instance_id=database_id,
            container_name=container_name,
            engine=database_type,
            username=old_username,
            db=db
        )
        
        # Update instance record
        await db.execute(text(f'''
            UPDATE "{INSTANCES_TABLE}"
            SET password = :password
            WHERE id = :id
        '''), {"password": new_password, "id": database_id})
        await db.commit()
        
        return {
            "message": "Credentials rotated successfully",
            "username": old_username,
            "password": new_password
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rotating credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/connection-string", dependencies=[Depends(require_permission("databases:read"))])
async def get_connection_string(database_id: int, db: AsyncSession = Depends(get_db)):
    """Get the connection string for the database."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT database_type, host, port, database_name, username, password
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        database_type = row[0]
        host = row[1]
        port = row[2]
        database_name = row[3]
        username = row[4]
        password = row[5]
        
        # Build connection string
        cred_mgr = CredentialManager()
        connection_string = cred_mgr.get_connection_string(
            engine=database_type,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            password=password
        )
        
        return {
            "connection_string": connection_string,
            "host": host,
            "port": port,
            "database": database_name,
            "username": username
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting connection string: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/databases", dependencies=[Depends(require_permission("databases:write"))])
async def create_inner_database(database_id: int, request: CreateInnerDatabaseRequest, db: AsyncSession = Depends(get_db)):
    """Create a database within the instance (for engines that support it)."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type, username, password
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        username = row[2]
        password = row[3]
        
        # Check if adapter supports databases
        adapter = get_adapter(database_type)
        if not adapter.supports_databases:
            raise HTTPException(
                status_code=400,
                detail=f"{database_type} does not support multiple databases"
            )
        
        # Create database
        db_ops = DatabaseOperations()
        await db_ops.create_database(
            container_name=container_name,
            engine=database_type,
            database_name=request.name,
            admin_username=username,
            admin_password=password
        )
        
        return {
            "message": f"Database '{request.name}' created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/databases", dependencies=[Depends(require_permission("databases:read"))])
async def list_inner_databases(database_id: int, db: AsyncSession = Depends(get_db)):
    """List databases within the instance."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type, username, password
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        username = row[2]
        password = row[3]
        
        # Check if adapter supports databases
        adapter = get_adapter(database_type)
        if not adapter.supports_databases:
            raise HTTPException(
                status_code=400,
                detail=f"{database_type} does not support multiple databases"
            )
        
        # List databases
        db_ops = DatabaseOperations()
        databases = await db_ops.list_databases(
            container_name=container_name,
            engine=database_type,
            admin_username=username,
            admin_password=password
        )
        
        return {
            "databases": databases,
            "count": len(databases)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/users", dependencies=[Depends(require_permission("databases:write"))])
async def create_inner_user(database_id: int, request: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    """Create a user within the instance (for engines that support it)."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type, username, password
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        admin_username = row[2]
        admin_password = row[3]
        
        # Check if adapter supports users
        adapter = get_adapter(database_type)
        if not adapter.supports_users:
            raise HTTPException(
                status_code=400,
                detail=f"{database_type} does not support user management"
            )
        
        # Generate password if not provided
        user_password = request.password
        if not user_password:
            cred_mgr = CredentialManager()
            user_password = cred_mgr.generate_password()
        
        # Create user
        db_ops = DatabaseOperations()
        await db_ops.create_user(
            container_name=container_name,
            engine=database_type,
            username=request.username,
            password=user_password,
            admin_username=admin_username,
            admin_password=admin_password,
            permissions=request.permissions
        )
        
        return {
            "message": f"User '{request.username}' created successfully",
            "username": request.username,
            "password": user_password
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/users", dependencies=[Depends(require_permission("databases:read"))])
async def list_inner_users(database_id: int, db: AsyncSession = Depends(get_db)):
    """List users within the instance."""
    try:
        # Get instance
        result = await db.execute(text(f'''
            SELECT container_name, database_type, username, password
            FROM "{INSTANCES_TABLE}"
            WHERE id = :id
        '''), {"id": database_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Database instance not found")
        
        container_name = row[0]
        database_type = row[1]
        admin_username = row[2]
        admin_password = row[3]
        
        # Check if adapter supports users
        adapter = get_adapter(database_type)
        if not adapter.supports_users:
            raise HTTPException(
                status_code=400,
                detail=f"{database_type} does not support user management"
            )
        
        # List users
        db_ops = DatabaseOperations()
        users = await db_ops.list_users(
            container_name=container_name,
            engine=database_type,
            admin_username=admin_username,
            admin_password=admin_password
        )
        
        return {
            "users": users,
            "count": len(users)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(status_code=500, detail=str(e))
