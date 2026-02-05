"""
Databases Module - Event Hooks

Handles module lifecycle events like enable/disable.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("uvicorn.error")


def get_data_dir() -> Path:
    """Get the Flux data directory."""
    # In production: /var/lib/flux
    # In development: project_root/data or uses module dir
    data_dir = os.environ.get("FLUX_DATA_DIR")
    if data_dir:
        return Path(data_dir)
    # Fallback to a local data directory relative to module
    return Path(__file__).parent / "data"


def get_containers_dir() -> Path:
    """Get the containers data directory for this module."""
    return get_data_dir() / "containers"


async def on_enable(data: dict, context) -> dict:
    """
    Called when the databases module is enabled.
    Creates necessary directories for container data.
    """
    logger.info("Databases module enabled - setting up directories")
    
    try:
        containers_dir = get_containers_dir()
        containers_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created containers directory: {containers_dir}")
        
        return {
            "success": True,
            "message": "Databases module initialized",
            "containers_dir": str(containers_dir)
        }
    except Exception as e:
        logger.warning(f"Could not create containers directory: {e}")
        # Don't fail the enable - just warn
        return {
            "success": True,
            "warning": f"Could not create containers directory: {e}"
        }


async def on_disable(data: dict, context) -> dict:
    """
    Called when the databases module is disabled.
    Note: Does NOT remove container data to prevent data loss.
    """
    logger.info("Databases module disabled")
    return {"success": True}


# Hook registration - these get registered when the module loads
HOOKS = {
    "after_module_enable": on_enable,
    "after_module_disable": on_disable,
}
