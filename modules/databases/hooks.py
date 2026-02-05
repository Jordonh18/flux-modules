"""
Databases Module - Event Hooks

Handles module lifecycle events like enable/disable.
Auto-installs Podman when the module is enabled.
"""

import asyncio
import logging
import os
import shutil
import subprocess
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


def is_podman_installed() -> bool:
    """Check if Podman is installed."""
    return shutil.which("podman") is not None


async def install_podman() -> dict:
    """
    Install Podman on the system.
    Supports Debian/Ubuntu systems.
    """
    logger.info("Installing Podman...")
    
    try:
        # Run apt update and install podman
        process = await asyncio.create_subprocess_exec(
            "sudo", "apt-get", "update",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.wait()
        
        process = await asyncio.create_subprocess_exec(
            "sudo", "apt-get", "install", "-y", "podman",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info("Podman installed successfully")
            return {"success": True, "message": "Podman installed successfully"}
        else:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"Failed to install Podman: {error_msg}")
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        logger.error(f"Error installing Podman: {e}")
        return {"success": False, "error": str(e)}


async def on_enable(data: dict, context) -> dict:
    """
    Called when the databases module is enabled.
    - Installs Podman if not present
    - Creates necessary directories for container data
    """
    logger.info("Databases module enabled - initializing...")
    results = {"success": True, "steps": []}
    
    # Step 1: Install Podman if needed
    if not is_podman_installed():
        logger.info("Podman not found - installing...")
        install_result = await install_podman()
        results["steps"].append({"action": "install_podman", **install_result})
        
        if not install_result.get("success"):
            results["warning"] = "Podman installation failed - manual installation may be required"
    else:
        logger.info("Podman already installed")
        results["steps"].append({"action": "check_podman", "status": "already_installed"})
    
    # Step 2: Create containers directory
    try:
        containers_dir = get_containers_dir()
        containers_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created containers directory: {containers_dir}")
        results["steps"].append({
            "action": "create_directories",
            "success": True,
            "path": str(containers_dir)
        })
    except Exception as e:
        logger.warning(f"Could not create containers directory: {e}")
        results["steps"].append({
            "action": "create_directories",
            "success": False,
            "error": str(e)
        })
    
    results["message"] = "Databases module initialized"
    return results


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
