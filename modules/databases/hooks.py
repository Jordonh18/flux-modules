"""
Databases Module - Event Hooks

Handles module lifecycle events like enable/disable.
Auto-installs Podman when the module is enabled.
Creates required data directories for containers, backups, and logs.

Module ID: 620600
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path

from . import MODULE_ID, MODULE_NAME, TABLE_PREFIX

logger = logging.getLogger("uvicorn.error")


# =============================================================================
# Directory Helpers
# =============================================================================

def get_data_dir() -> Path:
    """Get the Flux data directory for this module."""
    # In production: /var/lib/flux
    # In development: project_root/data or uses module dir
    data_dir = os.environ.get("FLUX_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "modules" / MODULE_NAME
    # Fallback to a local data directory relative to module
    return Path(__file__).parent / "data"


def get_containers_dir() -> Path:
    """Get the containers data directory."""
    return get_data_dir() / "containers"


def get_backups_dir() -> Path:
    """Get the backups data directory."""
    return get_data_dir() / "backups"


def get_logs_dir() -> Path:
    """Get the logs data directory."""
    return get_data_dir() / "logs"


def get_tls_dir() -> Path:
    """Get the TLS certificates directory."""
    return get_data_dir() / "tls"


def is_podman_installed() -> bool:
    """Check if Podman is installed."""
    return shutil.which("podman") is not None


# =============================================================================
# Podman Installation
# =============================================================================

async def install_podman() -> dict:
    """
    Install Podman on the system.
    Supports Debian/Ubuntu systems.
    """
    logger.info("Installing Podman...")

    try:
        process = await asyncio.create_subprocess_exec(
            "sudo", "apt-get", "update",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.wait()

        process = await asyncio.create_subprocess_exec(
            "sudo", "apt-get", "install", "-y", "podman",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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


# =============================================================================
# Lifecycle Hooks
# =============================================================================

async def on_enable(data: dict, context) -> dict:
    """
    Called when the databases module is enabled.
    - Installs Podman if not present
    - Creates necessary data directories (containers, backups, logs, tls)
    """
    logger.info(f"Databases module (ID: {MODULE_ID}) enabled — initializing...")
    results = {"success": True, "steps": []}

    # Step 1: Install Podman if needed
    if not is_podman_installed():
        logger.info("Podman not found — installing...")
        install_result = await install_podman()
        results["steps"].append({"action": "install_podman", **install_result})

        if not install_result.get("success"):
            results["warning"] = "Podman installation failed — manual installation may be required"
    else:
        logger.info("Podman already installed")
        results["steps"].append({"action": "check_podman", "status": "already_installed"})

    # Step 2: Create all required data directories
    directories = {
        "containers": get_containers_dir(),
        "backups": get_backups_dir(),
        "logs": get_logs_dir(),
        "tls": get_tls_dir(),
    }

    for dir_name, dir_path in directories.items():
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created {dir_name} directory: {dir_path}")
            results["steps"].append({
                "action": f"create_{dir_name}_dir",
                "success": True,
                "path": str(dir_path),
            })
        except Exception as e:
            logger.warning(f"Could not create {dir_name} directory: {e}")
            results["steps"].append({
                "action": f"create_{dir_name}_dir",
                "success": False,
                "error": str(e),
            })

    results["message"] = f"Databases module (ID: {MODULE_ID}) initialized"
    return results


async def on_disable(data: dict, context) -> dict:
    """
    Called when the databases module is disabled.
    Note: Does NOT remove container data or backups to prevent data loss.
    Containers remain in their current state (running or stopped).
    """
    logger.info(f"Databases module (ID: {MODULE_ID}) disabled — containers preserved")
    return {
        "success": True,
        "message": "Module disabled. Containers and data remain intact.",
    }


# =============================================================================
# Hook Registration — loaded by Flux module loader via module.json
# =============================================================================

HOOKS = {
    "after_module_enable": on_enable,
    "after_module_disable": on_disable,
}
