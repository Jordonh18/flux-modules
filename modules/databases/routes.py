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
)
from database import get_db_context
from enum import Enum
import secrets
import asyncio

# Import from module's own services (self-contained)
from .services.container_service import (
    ContainerService,
    DatabaseType,
    ContainerStatus,
    DatabaseCredentials,
)
from .services.volume_service import VolumeService

# Create router
router = ModuleRouter("databases")


# ============================================================================
# SKU Definitions (Azure-style tiers)
# ============================================================================

SKU_DEFINITIONS = {
    # B-series: Burstable (Cost-Effective for Variable Workloads)
    "b1": {"memory_mb": 1024, "cpus": 0.5, "storage_gb": 10},
    "b2": {"memory_mb": 2048, "cpus": 1.0, "storage_gb": 20},
    "b4": {"memory_mb": 4096, "cpus": 2.0, "storage_gb": 40},
    
    # D-series: General Purpose (Balanced CPU-to-Memory Ratio)
    "d2": {"memory_mb": 4096, "cpus": 2.0, "storage_gb": 50},
    "d4": {"memory_mb": 8192, "cpus": 4.0, "storage_gb": 100},
    "d8": {"memory_mb": 16384, "cpus": 8.0, "storage_gb": 200},
    "d16": {"memory_mb": 32768, "cpus": 16.0, "storage_gb": 500},
    "d32": {"memory_mb": 65536, "cpus": 32.0, "storage_gb": 1024},
    "d64": {"memory_mb": 131072, "cpus": 64.0, "storage_gb": 2048},
    
    # E-series: Memory Optimized (High Memory-to-CPU Ratio)
    "e2": {"memory_mb": 8192, "cpus": 2.0, "storage_gb": 50},
    "e4": {"memory_mb": 16384, "cpus": 4.0, "storage_gb": 100},
    "e8": {"memory_mb": 32768, "cpus": 8.0, "storage_gb": 200},
    "e16": {"memory_mb": 65536, "cpus": 16.0, "storage_gb": 500},
    "e32": {"memory_mb": 131072, "cpus": 32.0, "storage_gb": 1024},
    "e64": {"memory_mb": 262144, "cpus": 64.0, "storage_gb": 2048},
    
    # F-series: Compute Optimized (High CPU-to-Memory Ratio)
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

class DatabaseTypeEnum(str, Enum):
    """Database types available for creation"""
    postgresql = "postgresql"
    mysql = "mysql"
    mariadb = "mariadb"
    mongodb = "mongodb"
    redis = "redis"
    sqlserver = "sqlserver"
    cassandra = "cassandra"
    couchdb = "couchdb"
    neo4j = "neo4j"
    influxdb = "influxdb"
    elasticsearch = "elasticsearch"


class CreateDatabaseRequest(BaseModel):
    """Request to create a new database"""
    type: DatabaseTypeEnum
    name: Optional[str] = None
    database_name: str = "app"
    sku: str = "d1"
    memory_limit_mb: Optional[int] = None
    cpu_limit: Optional[float] = None
    storage_limit_gb: Optional[int] = None
    external_access: bool = False
    tls_enabled: bool = False
    tls_cert: Optional[str] = None  # Base64 encoded certificate
    tls_key: Optional[str] = None   # Base64 encoded key


class DatabaseInfo(BaseModel):
    """Database container information"""
    id: str
    name: str
    type: str
    status: str
    host: str
    port: int
    database: str
    username: str
    password: str
    connection_string: str


class PodmanStatus(BaseModel):
    """Podman installation status"""
    installed: bool
    version: Optional[str] = None
    message: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/status")
async def get_status():
    """
    Get databases module status.
    """
    podman_installed, version = await ContainerService.check_podman_installed()
    return {
        "status": "ok",
        "message": "Databases module is running",
        "podman": {
            "installed": podman_installed,
            "version": version,
        }
    }


@router.get("/requirements")
async def get_requirements():
    """
    Check system requirements for the databases module.
    Returns status and any setup instructions needed.
    """
    issues = []
    instructions = []
    
    # Check Podman
    podman_installed, version = await ContainerService.check_podman_installed()
    if not podman_installed:
        issues.append("Podman is not installed")
        instructions.append({
            "title": "Install Podman",
            "description": "Podman is required to run database containers",
            "action": "install_podman",
            "manual_command": "sudo apt install -y podman  # Debian/Ubuntu\nsudo dnf install -y podman  # Fedora/RHEL"
        })
    
    # Check if user can access podman (rootless)
    if podman_installed:
        try:
            info = await ContainerService.get_podman_info()
            if not info:
                issues.append("Cannot access Podman - check user permissions")
                instructions.append({
                    "title": "Configure Podman Access",
                    "description": "The flux user needs permission to run Podman",
                    "manual_command": "sudo usermod -aG podman flux  # Add flux user to podman group\nsudo loginctl enable-linger flux  # Enable lingering for systemd services"
                })
        except Exception:
            pass
    
    return {
        "ready": len(issues) == 0,
        "podman": {
            "installed": podman_installed,
            "version": version,
        },
        "issues": issues,
        "instructions": instructions,
    }


@router.get("/podman/status", response_model=PodmanStatus)
async def get_podman_status():
    """
    Check if Podman is installed and get version.
    """
    installed, version = await ContainerService.check_podman_installed()
    if installed:
        return PodmanStatus(
            installed=True,
            version=version,
            message="Podman is installed and ready"
        )
    return PodmanStatus(
        installed=False,
        version=None,
        message="Podman is not installed. Click 'Install Podman' to set it up."
    )


@router.post("/podman/install", response_model=PodmanStatus)
async def install_podman(current_user = Depends(require_permission("databases:write"))):
    """
    Attempt to install Podman on the system.
    Requires databases:write permission.
    """
    # First check if already installed
    installed, version = await ContainerService.check_podman_installed()
    if installed:
        return PodmanStatus(
            installed=True,
            version=version,
            message="Podman is already installed"
        )
    
    # Attempt installation
    success, message = await ContainerService.install_podman()
    
    if success:
        installed, version = await ContainerService.check_podman_installed()
        return PodmanStatus(
            installed=True,
            version=version,
            message=message
        )
    
    raise HTTPException(status_code=500, detail=message)


@router.get("/databases", response_model=List[dict])
async def list_databases(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    List all Flux-managed database containers.
    """
    # Get stored credentials from database first
    result = await db.execute(text("""
        SELECT id, container_id, container_name, database_type, host, port, 
               database_name, username, password, status, error_message, created_at,
               sku, memory_limit_mb, cpu_limit, storage_limit_gb, external_access, tls_enabled
        FROM module_databases
        ORDER BY created_at DESC
    """))
    stored_dbs = result.fetchall()
    
    # Get container names we're tracking
    container_names = [row.container_name for row in stored_dbs]
    
    # Get containers from Podman (only the ones we're tracking)
    containers = await ContainerService.list_flux_containers(container_names)
    
    # Merge container status with stored info
    databases = []
    container_map = {c.name: c for c in containers}
    
    for row in stored_dbs:
        container = container_map.get(row.container_name)
        
        # Always prefer real container status when container exists
        if container:
            status = container.status.value
            # Map container statuses to user-friendly names
            if status in ['exited', 'created']:
                status = 'stopped'
        elif row.status == 'error':
            # Show error status if no container and DB says error
            status = 'error'
        elif row.status == 'creating':
            # Show creating if no container yet
            status = 'creating'
        else:
            status = 'stopped'
        
        databases.append({
            "id": row.id,
            "name": row.container_name,
            "type": row.database_type,
            "status": status,
            "host": row.host,
            "port": row.port,
            "database": row.database_name,
            "username": row.username,
            "password": row.password,
            "created_at": row.created_at,
            "error_message": row.error_message if status == 'error' else None,
            "sku": row.sku,
            "memory_limit_mb": row.memory_limit_mb,
            "cpu_limit": row.cpu_limit,
            "storage_limit_gb": row.storage_limit_gb,
            "external_access": row.external_access,
            "tls_enabled": row.tls_enabled,
        })
    
    return databases


@router.post("/databases", response_model=dict)
async def create_database(
    request: CreateDatabaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Create a new database container.
    Creates the database record immediately and updates status as container is created.
    """
    # Check Podman is available
    installed, _ = await ContainerService.check_podman_installed()
    if not installed:
        raise HTTPException(
            status_code=400,
            detail="Podman is not installed. Please install Podman first."
        )
    
    # Map enum to DatabaseType
    db_type = DatabaseType(request.type.value)
    
    # Validate TLS configuration (CRITICAL FIX)
    if request.tls_enabled:
        if not request.tls_cert or not request.tls_key:
            raise HTTPException(
                status_code=400,
                detail="TLS enabled requires both certificate and private key"
            )
    
    # Apply SKU resources or use custom values
    if request.sku == "custom":
        # Use provided custom values
        memory_limit_mb = request.memory_limit_mb
        cpu_limit = request.cpu_limit
        storage_limit_gb = request.storage_limit_gb
        
        # Validate custom values are provided
        if not memory_limit_mb or not cpu_limit or not storage_limit_gb:
            raise HTTPException(
                status_code=400,
                detail="Custom SKU requires memory_limit_mb, cpu_limit, and storage_limit_gb"
            )
        
        # Validate custom resource limits (MAJOR FIX)
        if memory_limit_mb < 512 or memory_limit_mb > 65536:
            raise HTTPException(
                status_code=400,
                detail="Memory must be between 512MB and 64GB"
            )
        if cpu_limit < 0.5 or cpu_limit > 32:
            raise HTTPException(
                status_code=400,
                detail="CPU must be between 0.5 and 32 vCPUs"
            )
        if storage_limit_gb < 10 or storage_limit_gb > 1000:
            raise HTTPException(
                status_code=400,
                detail="Storage must be between 10GB and 1000GB"
            )
    else:
        # Apply SKU tier resources
        if request.sku not in SKU_DEFINITIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid SKU tier: {request.sku}. Must be one of: {', '.join(SKU_DEFINITIONS.keys())}"
            )
        
        sku_config = SKU_DEFINITIONS[request.sku]
        memory_limit_mb = sku_config["memory_mb"]
        cpu_limit = sku_config["cpus"]
        storage_limit_gb = sku_config["storage_gb"]
    
    # Get already-used ports from database (including creating databases)
    port_result = await db.execute(text("SELECT port FROM module_databases"))
    used_ports = {row.port for row in port_result.fetchall()}
    
    # Generate container name and credentials upfront
    suffix = secrets.token_hex(4)
    if request.name:
        # Use user's chosen name + UUID (no extra prefixes)
        container_name = f"{request.name}-{suffix}"
    else:
        # Fallback to db type + UUID
        container_name = f"{db_type.value}-{suffix}"
    
    username = ContainerService.generate_username()
    password = ContainerService.generate_password()
    host_port = ContainerService.find_available_port(exclude_ports=used_ports)
    
    try:
        # Insert database record immediately with 'creating' status and config
        result = await db.execute(text("""
            INSERT INTO module_databases 
            (container_id, container_name, database_type, host, port, database_name, username, password, status,
             sku, memory_limit_mb, cpu_limit, storage_limit_gb, external_access, tls_enabled)
            VALUES (:container_id, :container_name, :database_type, :host, :port, :database_name, :username, :password, 'creating',
                    :sku, :memory_limit_mb, :cpu_limit, :storage_limit_gb, :external_access, :tls_enabled)
            RETURNING id
        """), {
            "container_id": None,  # Will be updated when container is created
            "container_name": container_name,
            "database_type": db_type.value,
            "host": "localhost",
            "port": host_port,
            "database_name": request.database_name,
            "username": username,
            "password": password,
            "sku": request.sku,
            "memory_limit_mb": memory_limit_mb,
            "cpu_limit": cpu_limit,
            "storage_limit_gb": storage_limit_gb,
            "external_access": request.external_access,
            "tls_enabled": request.tls_enabled,
        })
        db_id = result.scalar()
        await db.commit()
        
        # Create container in background task
        async def create_container_background():
            """Background task to create container and update status"""
            try:
                # Handle TLS cert upload if provided
                tls_cert_path = None
                tls_key_path = None
                if request.tls_enabled and request.tls_cert and request.tls_key:
                    # Create volumes first (needed for TLS cert storage)
                    VolumeService.create_volumes(container_name)
                    
                    # Save TLS certificates
                    tls_paths = VolumeService.save_tls_certs(
                        container_name,
                        request.tls_cert,
                        request.tls_key
                    )
                    tls_cert_path = tls_paths["cert_path"]
                    tls_key_path = tls_paths["key_path"]
                    
                    # Update database record with TLS paths
                    try:
                        async with get_db_context() as background_db:
                            await background_db.execute(text("""
                                UPDATE module_databases 
                                SET tls_cert_path = :tls_cert_path, tls_key_path = :tls_key_path, updated_at = datetime('now')
                                WHERE id = :id
                            """), {
                                "tls_cert_path": tls_cert_path,
                                "tls_key_path": tls_key_path,
                                "id": db_id
                            })
                    except Exception as db_error:
                        print(f"Failed to update TLS paths: {db_error}")
                
                credentials = await ContainerService.create_database(
                    db_type=db_type,
                    name=request.name,
                    database_name=request.database_name,
                    container_name=container_name,
                    username=username,
                    password=password,
                    host_port=host_port,
                    external_access=request.external_access,
                    memory_limit_mb=memory_limit_mb,
                    cpu_limit=cpu_limit,
                    tls_cert_path=tls_cert_path,
                    tls_key_path=tls_key_path,
                )
                
                # Update record with container ID and success status
                try:
                    async with get_db_context() as background_db:
                        await background_db.execute(text("""
                            UPDATE module_databases 
                            SET container_id = :container_id, volume_path = :volume_path, status = 'running', error_message = NULL, updated_at = datetime('now')
                            WHERE id = :id
                        """), {
                            "container_id": credentials.container_id,
                            "volume_path": credentials.volume_path,
                            "id": db_id
                        })
                except Exception as db_error:
                    print(f"Failed to update database status: {db_error}")
                    
            except Exception as container_error:
                print(f"Container creation failed: {container_error}")
                # Update record with error status
                try:
                    async with get_db_context() as background_db:
                        await background_db.execute(text("""
                            UPDATE module_databases 
                            SET status = 'error', error_message = :error, updated_at = datetime('now')
                            WHERE id = :id
                        """), {
                            "error": str(container_error),
                            "id": db_id
                        })
                except Exception as db_error:
                    print(f"Failed to update error status: {db_error}")
        
        # Start background task (don't await)
        asyncio.create_task(create_container_background())
        
        # Return immediately
        return {
            "success": True,
            "message": f"{db_type.value} database creation started",
            "database": {
                "id": db_id,
                "name": container_name,
                "type": db_type.value,
                "host": "localhost",
                "port": host_port,
                "database": request.database_name,
                "username": username,
                "password": password,
                "status": "creating",
                "sku": request.sku,
                "memory_limit_mb": memory_limit_mb,
                "cpu_limit": cpu_limit,
                "storage_limit_gb": storage_limit_gb,
                "external_access": request.external_access,
                "tls_enabled": request.tls_enabled,
            }
        }
        
    except Exception as e:
        # Rollback database transaction on any error
        await db.rollback()
        
        # Extract clean error message
        error_msg = str(e)
        if "already in use" in error_msg.lower() or "unique" in error_msg.lower():
            error_msg = "A database with this name already exists. Please try again."
        elif "timeout" in error_msg.lower():
            error_msg = "Database creation timed out. The image may still be downloading. Please try again in a moment."
        
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/databases/{database_id}/start")
async def start_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Start a stopped database container.
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    success = await ContainerService.start_container(row.container_name)
    if success:
        # Clear any stale error messages when container starts successfully
        await db.execute(text("""
            UPDATE module_databases 
            SET status = 'running', error_message = NULL, updated_at = datetime('now')
            WHERE id = :id
        """), {"id": database_id})
        await db.commit()
        return {"success": True, "message": "Database started"}
    raise HTTPException(status_code=500, detail="Failed to start database")


@router.post("/databases/{database_id}/stop")
async def stop_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Stop a running database container.
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    success = await ContainerService.stop_container(row.container_name)
    if success:
        return {"success": True, "message": "Database stopped"}
    raise HTTPException(status_code=500, detail="Failed to stop database")


@router.post("/databases/{database_id}/restart")
async def restart_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Restart a database container.
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    success = await ContainerService.restart_container(row.container_name)
    if success:
        # Clear any stale error messages when container restarts successfully
        await db.execute(text("""
            UPDATE module_databases 
            SET status = 'running', error_message = NULL, updated_at = datetime('now')
            WHERE id = :id
        """), {"id": database_id})
        await db.commit()
        return {"success": True, "message": "Database restarted"}
    raise HTTPException(status_code=500, detail="Failed to restart database")


@router.delete("/databases/{database_id}")
async def delete_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Delete a database container and its stored credentials.
    Also removes persistent storage volumes.
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Remove container (force stop if running)
    await ContainerService.remove_container(row.container_name, force=True)
    
    # Cleanup persistent volumes
    try:
        VolumeService.cleanup_volumes(row.container_name)
    except Exception as vol_error:
        print(f"Warning: Failed to cleanup volumes for {row.container_name}: {vol_error}")
    
    # Remove from database
    await db.execute(text("DELETE FROM module_databases WHERE id = :id"), {"id": database_id})
    await db.commit()
    
    return {"success": True, "message": "Database deleted"}


@router.get("/databases/{database_id}/logs")
async def get_database_logs(
    database_id: int,
    lines: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    Get logs from a database container.
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    logs = await ContainerService.get_container_logs(row.container_name, lines)
    return {"logs": logs}


@router.get("/databases/{database_id}/stats")
async def get_database_stats(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    Get container resource stats (CPU, memory, network, disk).
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    stats = await ContainerService.get_container_stats(row.container_name)
    return stats


@router.get("/databases/{database_id}/inspect")
async def inspect_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    Get detailed container information.
    """
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Get container inspect info
    inspect_info = await ContainerService.get_container_inspect(row.container_name)
    
    # Get database size
    db_type = DatabaseType(row.database_type)
    size_info = await ContainerService.get_database_size(
        row.container_name, db_type, row.database_name, row.username, row.password
    )
    
    return {
        "container": inspect_info,
        "database_size": size_info,
    }


@router.post("/databases/{database_id}/backup")
async def backup_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Create a backup of the database.
    Returns the backup file path.
    """
    import os
    from datetime import datetime
    
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Create backups directory
    backup_dir = os.path.expanduser("~/.flux/backups/databases")
    os.makedirs(backup_dir, exist_ok=True)
    
    # Generate backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{row.container_name}_{timestamp}.sql"
    if row.database_type == "mongodb":
        backup_filename = f"{row.container_name}_{timestamp}.archive"
    elif row.database_type == "redis":
        backup_filename = f"{row.container_name}_{timestamp}.rdb"
    
    backup_path = os.path.join(backup_dir, backup_filename)
    
    db_type = DatabaseType(row.database_type)
    success, message = await ContainerService.backup_database(
        row.container_name, db_type, row.database_name, row.username, row.password, backup_path
    )
    
    if success:
        # Store backup record
        await db.execute(text("""
            INSERT INTO module_database_backups (database_id, backup_path, backup_size, created_at)
            VALUES (:database_id, :backup_path, :backup_size, datetime('now'))
        """), {
            "database_id": database_id,
            "backup_path": backup_path,
            "backup_size": os.path.getsize(backup_path) if os.path.exists(backup_path) else 0,
        })
        await db.commit()
        
        return {"success": True, "message": message, "backup_path": backup_path}
    
    raise HTTPException(status_code=500, detail=message)


@router.get("/databases/{database_id}/backups")
async def list_database_backups(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    List all backups for a database.
    """
    result = await db.execute(text("""
        SELECT id, backup_path, backup_size, created_at
        FROM module_database_backups
        WHERE database_id = :database_id
        ORDER BY created_at DESC
    """), {"database_id": database_id})
    
    backups = []
    for row in result.fetchall():
        backups.append({
            "id": row.id,
            "path": row.backup_path,
            "size": row.backup_size,
            "created_at": row.created_at,
        })
    
    return {"backups": backups}


@router.post("/databases/{database_id}/restore/{backup_id}")
async def restore_database(
    database_id: int,
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Restore a database from a backup.
    """
    # Get database info
    db_result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    db_row = db_result.fetchone()
    
    if not db_row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Get backup info
    backup_result = await db.execute(text(
        "SELECT backup_path FROM module_database_backups WHERE id = :id AND database_id = :database_id"
    ), {"id": backup_id, "database_id": database_id})
    backup_row = backup_result.fetchone()
    
    if not backup_row:
        raise HTTPException(status_code=404, detail="Backup not found")
    
    db_type = DatabaseType(db_row.database_type)
    success, message = await ContainerService.restore_database(
        db_row.container_name, db_type, db_row.database_name, 
        db_row.username, db_row.password, backup_row.backup_path
    )
    
    if success:
        return {"success": True, "message": message}
    
    raise HTTPException(status_code=500, detail=message)


@router.delete("/databases/{database_id}/backups/{backup_id}")
async def delete_backup(
    database_id: int,
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Delete a backup file.
    """
    import os
    
    result = await db.execute(text(
        "SELECT backup_path FROM module_database_backups WHERE id = :id AND database_id = :database_id"
    ), {"id": backup_id, "database_id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Backup not found")
    
    # Delete file
    if os.path.exists(row.backup_path):
        os.remove(row.backup_path)
    
    # Delete record
    await db.execute(text("DELETE FROM module_database_backups WHERE id = :id"), {"id": backup_id})
    await db.commit()
    
    return {"success": True, "message": "Backup deleted"}


@router.get("/databases/{database_id}/tables")
async def list_tables(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    List all tables in the database.
    """
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    db_type = DatabaseType(row.database_type)
    tables = await ContainerService.list_database_tables(
        row.container_name, db_type, row.database_name, row.username, row.password
    )
    
    return {"tables": tables}


@router.get("/databases/{database_id}/tables/{table_name}/schema")
async def get_table_schema(
    database_id: int,
    table_name: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    Get the schema/structure of a specific table.
    """
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    db_type = DatabaseType(row.database_type)
    schema = await ContainerService.get_table_schema(
        row.container_name, db_type, row.database_name, row.username, row.password, table_name
    )
    
    return {"schema": schema}


@router.get("/databases/{database_id}/tables/{table_name}/data")
async def get_table_data(
    database_id: int,
    table_name: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    Get sample data from a specific table.
    """
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    db_type = DatabaseType(row.database_type)
    data = await ContainerService.get_table_data(
        row.container_name, db_type, row.database_name, row.username, row.password, table_name, limit
    )
    
    return {"data": data}
