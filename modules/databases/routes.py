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
import sys
import os

# Add server to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))
from services.container_service import (
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
@require_permission("databases:write")
async def install_podman():
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
@require_permission("databases:read")
async def list_databases(db: AsyncSession = Depends(get_db)):
    """
    List all Flux-managed database containers.
    """
    # Get containers from Podman
    containers = await ContainerService.list_flux_containers()
    
    # Get stored credentials from database
    result = await db.execute(text("""
        SELECT id, container_id, container_name, database_type, host, port, 
               database_name, username, password, created_at
        FROM module_databases
        ORDER BY created_at DESC
    """))
    stored_dbs = result.fetchall()
    
    # Merge container status with stored info
    databases = []
    container_map = {c.name: c for c in containers}
    
    for row in stored_dbs:
        container = container_map.get(row.container_name)
        databases.append({
            "id": row.id,
            "container_id": row.container_id,
            "name": row.container_name,
            "type": row.database_type,
            "status": container.status.value if container else "unknown",
            "host": row.host,
            "port": row.port,
            "database": row.database_name,
            "username": row.username,
            "password": row.password,
            "created_at": row.created_at,
        })
    
    return databases


@router.post("/databases", response_model=dict)
@require_permission("databases:write")
async def create_database(
    request: CreateDatabaseRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new database container.
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
    
    try:
        # Create the database container
        credentials = await ContainerService.create_database(
            db_type=db_type,
            name=request.name,
            database_name=request.database_name
        )
        
        # Store credentials in database
        await db.execute(text("""
            INSERT INTO module_databases 
            (container_id, container_name, database_type, host, port, database_name, username, password)
            VALUES (:container_id, :container_name, :database_type, :host, :port, :database_name, :username, :password)
        """), {
            "container_id": credentials.container_id,
            "container_name": credentials.container_name,
            "database_type": credentials.database_type.value,
            "host": credentials.host,
            "port": credentials.port,
            "database_name": credentials.database,
            "username": credentials.username,
            "password": credentials.password,
        })
        await db.commit()
        
        return {
            "success": True,
            "message": f"{db_type.value} database created successfully",
            "database": credentials.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/start")
@require_permission("databases:write")
async def start_database(database_id: int, db: AsyncSession = Depends(get_db)):
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
@require_permission("databases:write")
async def stop_database(database_id: int, db: AsyncSession = Depends(get_db)):
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
@require_permission("databases:write")
async def delete_database(database_id: int, db: AsyncSession = Depends(get_db)):
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
@require_permission("databases:read")
async def get_database_logs(database_id: int, lines: int = 100, db: AsyncSession = Depends(get_db)):
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

