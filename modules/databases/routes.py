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
    # VNet hooks
    allocate_vnet_ip,
    release_vnet_ip,
    get_module_allocations,
    list_available_vnets,
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

class DatabaseTypeEnum(str, Enum):
    """Database types available for creation"""
    postgresql = "postgresql"
    mysql = "mysql"
    mariadb = "mariadb"
    mongodb = "mongodb"
    redis = "redis"


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
    vnet_name: Optional[str] = None  # VNet to connect to (optional)


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


@router.get("/system-info")
async def get_system_info():
    """
    Get host system information (CPU cores, RAM).
    Used to filter database SKUs that exceed system capacity.
    """
    import os
    
    # Get CPU count
    cpu_cores = os.cpu_count() or 1
    
    # Get total RAM from /proc/meminfo (Linux)
    total_memory_mb = 0
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    # MemTotal is in KB, convert to MB
                    total_memory_kb = int(line.split()[1])
                    total_memory_mb = total_memory_kb // 1024
                    break
    except Exception:
        # Fallback to a conservative estimate if we can't read meminfo
        total_memory_mb = 4096  # 4GB default
    
    return {
        "cpu_cores": cpu_cores,
        "total_memory_mb": total_memory_mb,
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
        FROM databases_instances
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
    port_result = await db.execute(text("SELECT port FROM databases_instances"))
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
    
    # Try to allocate a VNet IP for this database (optional - falls back to port mapping)
    vnet_ip = None
    vnet_id = None
    vnet_bridge = None
    if allocate_vnet_ip is not None and request.vnet_name:
        try:
            # Use the user-selected VNet
            allocation = await allocate_vnet_ip(
                vnet_name=request.vnet_name,
                module_name="databases",
                resource_id=container_name,
                label=f"{db_type.value} - {request.name or container_name}",
            )
            if allocation:
                vnet_ip = allocation.get("ip_address")
                vnet_id = allocation.get("vnet_id")
                # Get VNet details to find bridge name
                vnets = await list_available_vnets()
                selected_vnet = next((v for v in vnets if v["name"] == request.vnet_name), None)
                if selected_vnet:
                    vnet_bridge = selected_vnet.get("bridge_name")
        except Exception as vnet_err:
            # VNet allocation is best-effort; log and continue with port mapping
            print(f"VNet allocation failed: {vnet_err}")
    
    # Connection host is VNet IP if allocated, otherwise localhost
    connection_host = vnet_ip if vnet_ip else "localhost"
    connection_port = host_port  # Port mapping still used as fallback/alongside
    
    try:
        # Insert database record immediately with 'creating' status and config
        result = await db.execute(text("""
            INSERT INTO databases_instances 
            (container_id, container_name, database_type, host, port, database_name, username, password, status,
             sku, memory_limit_mb, cpu_limit, storage_limit_gb, external_access, tls_enabled)
            VALUES (:container_id, :container_name, :database_type, :host, :port, :database_name, :username, :password, 'creating',
                    :sku, :memory_limit_mb, :cpu_limit, :storage_limit_gb, :external_access, :tls_enabled)
            RETURNING id
        """), {
            "container_id": None,  # Will be updated when container is created
            "container_name": container_name,
            "database_type": db_type.value,
            "host": connection_host,
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
                                UPDATE databases_instances 
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
                    sku=request.sku,
                    tls_cert_path=tls_cert_path,
                    tls_key_path=tls_key_path,
                    vnet_bridge=vnet_bridge,
                    vnet_ip=vnet_ip,
                )
                
                # Update record with container ID and success status
                try:
                    async with get_db_context() as background_db:
                        await background_db.execute(text("""
                            UPDATE databases_instances 
                            SET container_id = :container_id, volume_path = :volume_path, 
                                host = :host, port = :port,
                                status = 'running', error_message = NULL, updated_at = datetime('now')
                            WHERE id = :id
                        """), {
                            "container_id": credentials.container_id,
                            "volume_path": credentials.volume_path,
                            "host": credentials.host,
                            "port": credentials.port,
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
                            UPDATE databases_instances 
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
                "host": connection_host,
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
                "vnet_ip": vnet_ip,
                "vnet_bridge": vnet_bridge,
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
        "SELECT container_name FROM databases_instances WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    success = await ContainerService.start_container(row.container_name)
    if success:
        # Clear any stale error messages when container starts successfully
        await db.execute(text("""
            UPDATE databases_instances 
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
        "SELECT container_name FROM databases_instances WHERE id = :id"
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
        "SELECT container_name FROM databases_instances WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    success = await ContainerService.restart_container(row.container_name)
    if success:
        # Clear any stale error messages when container restarts successfully
        await db.execute(text("""
            UPDATE databases_instances 
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
        "SELECT container_name FROM databases_instances WHERE id = :id"
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
    
    # Release VNet IP allocation if available
    if release_vnet_ip is not None:
        try:
            await release_vnet_ip(module_name="databases", resource_id=row.container_name)
        except Exception as vnet_err:
            print(f"Warning: Failed to release VNet IP for {row.container_name}: {vnet_err}")
    
    # Remove from database
    await db.execute(text("DELETE FROM databases_instances WHERE id = :id"), {"id": database_id})
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
        "SELECT container_name FROM databases_instances WHERE id = :id"
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
        "SELECT container_name FROM databases_instances WHERE id = :id"
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
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
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


@router.post("/databases/{database_id}/snapshot")
async def snapshot_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Create a snapshot of the database.
    Returns the snapshot file path.
    """
    import os
    from datetime import datetime
    
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Create snapshots directory
    snapshot_dir = os.path.expanduser("~/.flux/snapshots/databases")
    os.makedirs(snapshot_dir, exist_ok=True)
    
    # Generate snapshot filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_filename = f"{row.container_name}_{timestamp}.sql"
    if row.database_type == "mongodb":
        snapshot_filename = f"{row.container_name}_{timestamp}.archive"
    elif row.database_type == "redis":
        snapshot_filename = f"{row.container_name}_{timestamp}.rdb"
    
    snapshot_path = os.path.join(snapshot_dir, snapshot_filename)
    
    db_type = DatabaseType(row.database_type)
    success, message = await ContainerService.snapshot_database(
        row.container_name, db_type, row.database_name, row.username, row.password, snapshot_path
    )
    
    if success:
        # Store snapshot record
        await db.execute(text("""
            INSERT INTO databases_snapshots (database_id, snapshot_path, snapshot_size, created_at)
            VALUES (:database_id, :snapshot_path, :snapshot_size, datetime('now'))
        """), {
            "database_id": database_id,
            "snapshot_path": snapshot_path,
            "snapshot_size": os.path.getsize(snapshot_path) if os.path.exists(snapshot_path) else 0,
        })
        await db.commit()
        
        return {"success": True, "message": message, "snapshot_path": snapshot_path}
    
    raise HTTPException(status_code=500, detail=message)


@router.get("/databases/{database_id}/snapshots")
async def list_database_snapshots(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    List all snapshots for a database.
    """
    result = await db.execute(text("""
        SELECT id, snapshot_path, snapshot_size, created_at
        FROM databases_snapshots
        WHERE database_id = :database_id
        ORDER BY created_at DESC
    """), {"database_id": database_id})
    
    snapshots = []
    for row in result.fetchall():
        snapshots.append({
            "id": row.id,
            "path": row.snapshot_path,
            "size": row.snapshot_size,
            "created_at": row.created_at,
        })
    
    return {"snapshots": snapshots}


@router.post("/databases/{database_id}/restore/{snapshot_id}")
async def restore_database(
    database_id: int,
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Restore a database from a snapshot.
    """
    # Get database info
    db_result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
    ), {"id": database_id})
    db_row = db_result.fetchone()
    
    if not db_row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Get backup info
    snapshot_result = await db.execute(text(
        "SELECT snapshot_path FROM databases_snapshots WHERE id = :id AND database_id = :database_id"
    ), {"id": snapshot_id, "database_id": database_id})
    snapshot_row = snapshot_result.fetchone()
    
    if not snapshot_row:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    db_type = DatabaseType(db_row.database_type)
    success, message = await ContainerService.restore_database(
        db_row.container_name, db_type, db_row.database_name, 
        db_row.username, db_row.password, snapshot_row.snapshot_path
    )
    
    if success:
        return {"success": True, "message": message}
    
    raise HTTPException(status_code=500, detail=message)


@router.delete("/databases/{database_id}/snapshots/{snapshot_id}")
async def delete_snapshot(
    database_id: int,
    snapshot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Delete a snapshot file.
    """
    import os
    
    result = await db.execute(text(
        "SELECT snapshot_path FROM databases_snapshots WHERE id = :id AND database_id = :database_id"
    ), {"id": snapshot_id, "database_id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    # Delete file
    if os.path.exists(row.snapshot_path):
        os.remove(row.snapshot_path)
    
    # Delete record
    await db.execute(text("DELETE FROM databases_snapshots WHERE id = :id"), {"id": snapshot_id})
    await db.commit()
    
    return {"success": True, "message": "Snapshot deleted"}


@router.get("/databases/{database_id}/export")
async def export_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:read"))
):
    """
    Export database to a zip file using database-specific export methods.
    Returns a downloadable zip file.
    """
    import os
    import tempfile
    import zipfile
    from datetime import datetime
    from fastapi.responses import FileResponse
    
    result = await db.execute(text(
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Create temporary export directory
    export_dir = tempfile.mkdtemp(prefix="flux_db_export_")
    
    try:
        # Generate export filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"{row.container_name}_{timestamp}.sql"
        
        if row.database_type == "mongodb":
            export_filename = f"{row.container_name}_{timestamp}.archive"
        elif row.database_type == "redis":
            export_filename = f"{row.container_name}_{timestamp}.rdb"
        
        export_path = os.path.join(export_dir, export_filename)
        
        # Perform database export using backup method
        db_type = DatabaseType(row.database_type)
        success, message = await ContainerService.backup_database(
            row.container_name, db_type, row.database_name, row.username, row.password, export_path
        )
        
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        # Create zip file
        zip_filename = f"{row.container_name}_{timestamp}.zip"
        zip_path = os.path.join(export_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(export_path, os.path.basename(export_path))
        
        # Return zip file as download
        return FileResponse(
            path=zip_path,
            media_type='application/zip',
            filename=zip_filename,
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
        )
    
    except Exception as e:
        # Clean up on error
        import shutil
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


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
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
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
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
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
        "SELECT container_name, database_type, database_name, username, password FROM databases_instances WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    db_type = DatabaseType(row.database_type)
    data = await ContainerService.get_table_data(
        row.container_name, db_type, row.database_name, row.username, row.password, table_name, limit
    )
    
    return {"data": data}
