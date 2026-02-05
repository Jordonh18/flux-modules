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

# Create router
router = ModuleRouter("databases")


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/status")
async def get_status():
    """
    Get databases module status.
    """
    return {"status": "ok", "message": "Databases module is running"}
