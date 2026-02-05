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
from enum import Enum

# Import from module's own services (self-contained)
from .services.container_service import (
    ContainerService,
    DatabaseType,
    ContainerStatus,
    DatabaseCredentials,
)

# Create router
router = ModuleRouter("databases")


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
    # Get containers from Podman
    containers = await ContainerService.list_flux_containers()
    
    # Get stored credentials from database
    result = await db.execute(text("""
        SELECT id, container_id, container_name, database_type, host, port, 
               database_name, username, password, status, error_message, created_at
        FROM module_databases
        ORDER BY created_at DESC
    """))
    stored_dbs = result.fetchall()
    
    # Merge container status with stored info
    databases = []
    container_map = {c.name: c for c in containers}
    
    for row in stored_dbs:
        container = container_map.get(row.container_name)
        
        # Use database status if creating/error, otherwise use container status
        if row.status in ('creating', 'error'):
            status = row.status
        else:
            status = container.status.value if container else "unknown"
        
        databases.append({
            "id": row.id,
            "container_id": row.container_id,
            "name": row.container_name,
            "type": row.database_type,
            "status": status,
            "host": row.host,
            "port": row.port,
            "database": row.database_name,
            "username": row.username,
            "password": row.password,
            "created_at": row.created_at,
            "error_message": row.error_message if row.status == 'error' else None,
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
    
    # Generate container name and credentials upfront
    suffix = secrets.token_hex(4)
    if request.name:
        container_name = f"{ContainerService.CONTAINER_PREFIX}{request.name}-{suffix}"
    else:
        container_name = f"{ContainerService.CONTAINER_PREFIX}{db_type.value}-{suffix}"
    
    username = ContainerService.generate_username()
    password = ContainerService.generate_password()
    host_port = ContainerService.find_available_port()
    
    try:
        # Insert database record immediately with 'creating' status
        result = await db.execute(text("""
            INSERT INTO module_databases 
            (container_id, container_name, database_type, host, port, database_name, username, password, status)
            VALUES (:container_id, :container_name, :database_type, :host, :port, :database_name, :username, :password, 'creating')
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
        })
        db_id = result.scalar()
        await db.commit()
        
        # Now create the container (this can take time)
        try:
            credentials = await ContainerService.create_database(
                db_type=db_type,
                name=request.name,
                database_name=request.database_name,
                container_name=container_name,
                username=username,
                password=password,
                host_port=host_port
            )
            
            # Update record with container ID and success status
            await db.execute(text("""
                UPDATE module_databases 
                SET container_id = :container_id, status = 'running', updated_at = datetime('now')
                WHERE id = :id
            """), {
                "container_id": credentials.container_id,
                "id": db_id
            })
            await db.commit()
            
        except Exception as container_error:
            # Update record with error status
            await db.execute(text("""
                UPDATE module_databases 
                SET status = 'error', error_message = :error, updated_at = datetime('now')
                WHERE id = :id
            """), {
                "error": str(container_error),
                "id": db_id
            })
            await db.commit()
            # Don't raise - record is created, container just failed
        
        return {
            "success": True,
            "message": f"{db_type.value} database created successfully",
            "database": {
                "id": db_id,
                "name": container_name,
                "type": db_type.value,
                "host": "localhost",
                "port": host_port,
                "database": request.database_name,
                "username": username,
                "password": password,
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


@router.delete("/databases/{database_id}")
async def delete_database(
    database_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("databases:write"))
):
    """
    Delete a database container and its stored credentials.
    """
    result = await db.execute(text(
        "SELECT container_name FROM module_databases WHERE id = :id"
    ), {"id": database_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Database not found")
    
    # Remove container (force stop if running)
    await ContainerService.remove_container(row.container_name, force=True)
    
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

