"""
Volume Service for Databases Module

Manages persistent storage volumes for database containers.
Handles directory creation, permissions, and cleanup for rootless Podman.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional

# Configurable base storage path with default
VOLUME_BASE_PATH = os.environ.get("FLUX_DATABASES_PATH", "/flux/databases")

# Safe database name pattern: alphanumeric, dots, underscores, hyphens
# Must start with alphanumeric, max 64 chars
SAFE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$')


class VolumeService:
    """Manages volume creation and cleanup for database containers."""
    
    @staticmethod
    def validate_db_name(db_name: str) -> bool:
        """
        Validate database name is safe for filesystem operations.
        
        Checks:
        - Name is not empty
        - Matches safe pattern (alphanumeric, dots, underscores, hyphens)
        - No path separators or traversal sequences
        
        Args:
            db_name: Database name to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not db_name:
            return False
        if not SAFE_NAME_PATTERN.match(db_name):
            return False
        # Extra safety: reject any path components
        if '/' in db_name or '\\' in db_name or '..' in db_name:
            return False
        return True
    
    @staticmethod
    def _ensure_path_within_base(path: Path, base: Path) -> bool:
        """
        Ensure resolved path is within base directory.
        
        Protects against path traversal attacks by verifying the resolved
        absolute path is within the base directory.
        
        Args:
            path: Path to check
            base: Base directory path must be within
            
        Returns:
            True if path is within base, False otherwise
        """
        try:
            resolved_path = path.resolve()
            resolved_base = base.resolve()
            # Check if resolved path starts with base path
            return str(resolved_path).startswith(str(resolved_base) + os.sep) or resolved_path == resolved_base
        except (OSError, ValueError):
            return False
    
    @staticmethod
    def get_base_path() -> Path:
        """
        Get or create the base volume path.
        Creates /flux/databases if it doesn't exist.
        """
        path = Path(VOLUME_BASE_PATH)
        path.mkdir(parents=True, exist_ok=True, mode=0o755)
        return path
    
    @staticmethod
    def create_volumes(db_name: str) -> dict:
        """
        Create volume directories for a database.
        
        Creates a standardized directory structure for persistent storage:
        - /flux/databases/{db_name}/data - Main database data files
        - /flux/databases/{db_name}/config - Configuration files
        - /flux/databases/{db_name}/logs - Log files
        - /flux/databases/{db_name}/secrets - Sensitive data (0700 perms)
        
        Args:
            db_name: Name of the database (container name)
        
        Returns:
            dict with paths:
            {
                "base": "/flux/databases/{db_name}",
                "data": "/flux/databases/{db_name}/data",
                "config": "/flux/databases/{db_name}/config",
                "logs": "/flux/databases/{db_name}/logs",
                "secrets": "/flux/databases/{db_name}/secrets"
            }
        
        Raises:
            ValueError: If db_name is invalid or path traversal detected
            OSError: If directory creation fails
            PermissionError: If insufficient permissions
        """
        # Validate database name
        if not VolumeService.validate_db_name(db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        
        base_path = Path(VOLUME_BASE_PATH)
        target_path = base_path / db_name
        
        # Verify path is within base before creating (path traversal protection)
        if not VolumeService._ensure_path_within_base(target_path, base_path):
            raise ValueError(f"Path traversal detected: {db_name}")
        
        # Create directories with secure permissions
        paths = {
            "base": target_path,
            "data": target_path / "data",
            "config": target_path / "config",
            "logs": target_path / "logs",
            "secrets": target_path / "secrets"
        }
        
        for name, path in paths.items():
            path.mkdir(parents=True, exist_ok=True)
            # Secure permissions: secrets dir is 0700, others are 0755
            if name == "secrets":
                os.chmod(path, 0o700)
            else:
                os.chmod(path, 0o755)
        
        # Return string paths for use in container commands
        return {k: str(v) for k, v in paths.items()}
    
    @staticmethod
    def cleanup_volumes(db_name: str) -> bool:
        """
        Remove all volume directories for a database.
        
        Completely removes the database's persistent storage directory
        and all subdirectories. Use with caution - this is permanent.
        
        Args:
            db_name: Name of the database (container name)
        
        Returns:
            True if volumes were removed, False if they didn't exist or name invalid
        
        Raises:
            OSError: If removal fails due to permissions or other errors
        """
        # Validate database name
        if not VolumeService.validate_db_name(db_name):
            return False
        
        base_path = Path(VOLUME_BASE_PATH)
        target_path = base_path / db_name
        
        # Verify path is within base before deleting (path traversal protection)
        if not VolumeService._ensure_path_within_base(target_path, base_path):
            return False
        
        if target_path.exists():
            shutil.rmtree(target_path)
            return True
        return False
    
    @staticmethod
    def get_volume_paths(db_name: str) -> Optional[dict]:
        """
        Get volume paths if they exist.
        
        Args:
            db_name: Name of the database (container name)
        
        Returns:
            dict with paths if volumes exist, None otherwise
        """
        # Validate database name
        if not VolumeService.validate_db_name(db_name):
            return None
        
        base_path = Path(VOLUME_BASE_PATH)
        target_path = base_path / db_name
        
        # Verify path is within base (path traversal protection)
        if not VolumeService._ensure_path_within_base(target_path, base_path):
            return None
        
        if not target_path.exists():
            return None
        return {
            "base": str(target_path),
            "data": str(target_path / "data"),
            "config": str(target_path / "config"),
            "logs": str(target_path / "logs"),
            "secrets": str(target_path / "secrets")
        }
    
    @staticmethod
    def copy_config_template(db_name: str, db_type) -> str:
        """
        Copy configuration template to database's config directory.
        
        Copies the appropriate config template for the database type
        from the module's config_templates directory to the database's
        persistent config directory.
        
        Args:
            db_name: Name of the database (container name)
            db_type: Engine name (e.g., 'postgresql', 'mysql', 'redis')
        
        Returns:
            str: Path to the copied config file
        
        Raises:
            ValueError: If db_name is invalid or volumes don't exist
            FileNotFoundError: If config template doesn't exist
            OSError: If copy operation fails
        """
        # Validate database name
        if not VolumeService.validate_db_name(db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        
        # Verify volumes exist
        volume_paths = VolumeService.get_volume_paths(db_name)
        if not volume_paths:
            raise ValueError(f"Volume directory for {db_name} does not exist")
        
        # Get the database type string (handles both string and enum)
        db_type_str = db_type.value if hasattr(db_type, 'value') else str(db_type)
        
        # Get module root directory (go up from services/ to module root)
        module_dir = Path(__file__).parent.parent
        template_dir = module_dir / "config_templates" / db_type_str
        
        if not template_dir.exists():
            raise FileNotFoundError(f"Config template directory not found: {template_dir}")
        
        # Find .j2 template file in the engine directory
        template_files = list(template_dir.glob("*.j2"))
        if not template_files:
            raise FileNotFoundError(f"No .j2 template files found in {template_dir}")
        
        # Use the first .j2 file found (typically there's only one per engine)
        template_path = template_files[0]
        config_filename = template_path.stem  # Remove .j2 extension
        
        # Copy to config directory
        config_dir = Path(volume_paths["config"])
        destination_path = config_dir / config_filename
        
        shutil.copy2(template_path, destination_path)
        
        # Set secure permissions (readable by all, writable by owner)
        os.chmod(destination_path, 0o644)
        
        return str(destination_path)
    
    @staticmethod
    def create_secrets(db_name: str, root_password: str, user_password: Optional[str] = None) -> dict:
        """
        Create password files in secrets directory.
        
        Writes password files to the secrets directory with restrictive permissions
        to prevent exposure via container inspection tools like 'podman inspect'.
        
        Args:
            db_name: Name of the database (container name)
            root_password: Root/admin password
            user_password: Optional user password (for databases that support separate users)
        
        Returns:
            dict with paths to created secret files:
            {
                "root_password": "/flux/databases/{db_name}/secrets/root_password",
                "user_password": "/flux/databases/{db_name}/secrets/user_password"  # if provided
            }
        
        Raises:
            ValueError: If db_name is invalid
            OSError: If file creation or permission setting fails
        
        Security:
            - Files created with 0600 permissions (owner read/write only)
            - Directory created with 0700 permissions (owner access only)
        """
        if not VolumeService.validate_db_name(db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        
        base = Path(VOLUME_BASE_PATH) / db_name / "secrets"
        
        # Ensure secrets directory exists with secure perms
        base.mkdir(parents=True, exist_ok=True)
        os.chmod(base, 0o700)
        
        secrets = {}
        
        # Write root password
        root_path = base / "root_password"
        with open(root_path, 'w', encoding='utf-8') as f:
            f.write(root_password)
        os.chmod(root_path, 0o600)
        secrets["root_password"] = str(root_path)
        
        # Write user password if provided
        if user_password:
            user_path = base / "user_password"
            with open(user_path, 'w', encoding='utf-8') as f:
                f.write(user_password)
            os.chmod(user_path, 0o600)
            secrets["user_password"] = str(user_path)
        
        return secrets
    
    @staticmethod
    def save_tls_certs(db_name: str, cert_b64: str, key_b64: str) -> dict:
        """
        Save TLS certificates for database.
        
        Creates a TLS directory within the database volume and saves the
        certificate and key files. Files are base64 decoded and saved with
        secure permissions. Also creates a combined PEM file for MongoDB.
        
        Args:
            db_name: Name of the database (container name)
            cert_b64: Base64 encoded certificate
            key_b64: Base64 encoded private key
        
        Returns:
            dict with paths:
            {
                "cert_path": "/flux/databases/{db_name}/tls/server.crt",
                "key_path": "/flux/databases/{db_name}/tls/server.key",
                "combined_path": "/flux/databases/{db_name}/tls/combined.pem"
            }
        
        Raises:
            ValueError: If db_name is invalid, volumes don't exist, or cert/key exceed size limits
            OSError: If file operations fail
        
        Security:
            - Base64 decoding with validation enabled (MAJOR FIX)
            - Size limits enforced (10KB max per file) (MAJOR FIX)
            - TLS directory has 0700 permissions (MAJOR FIX)
            - TLS files have 0600 permissions (read/write for owner only)
            - Validates database name before operation
            - Ensures volumes exist before writing
        """
        import base64
        
        # Maximum certificate/key size: 10KB (MAJOR FIX)
        MAX_CERT_SIZE = 10 * 1024
        
        # Validate database name
        if not VolumeService.validate_db_name(db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        
        # Verify volumes exist
        volume_paths = VolumeService.get_volume_paths(db_name)
        if not volume_paths:
            raise ValueError(f"Volume directory for {db_name} does not exist")
        
        # Validate and decode with validation enabled (MAJOR FIX)
        try:
            cert_data = base64.b64decode(cert_b64, validate=True)
            key_data = base64.b64decode(key_b64, validate=True)
        except Exception as exc:
            raise ValueError("Invalid base64 encoding for certificate or key") from exc
        
        # Check size limits (MAJOR FIX)
        if len(cert_data) > MAX_CERT_SIZE or len(key_data) > MAX_CERT_SIZE:
            raise ValueError("Certificate or key exceeds maximum size of 10KB")
        
        # Create TLS directory with secure permissions (MAJOR FIX: 0700 instead of 0755)
        base_path = Path(VOLUME_BASE_PATH)
        tls_path = base_path / db_name / "tls"
        tls_path.mkdir(parents=True, exist_ok=True)
        os.chmod(tls_path, 0o700)
        
        # Save certificate
        cert_file = tls_path / "server.crt"
        cert_file.write_bytes(cert_data)
        os.chmod(cert_file, 0o600)
        
        # Save private key
        key_file = tls_path / "server.key"
        key_file.write_bytes(key_data)
        os.chmod(key_file, 0o600)
        
        # Create combined PEM file for MongoDB (CRITICAL FIX)
        combined_file = tls_path / "combined.pem"
        combined_file.write_bytes(cert_data + b"\n" + key_data)
        os.chmod(combined_file, 0o600)
        
        return {
            "cert_path": str(cert_file),
            "key_path": str(key_file),
            "combined_path": str(combined_file)
        }
    
    @staticmethod
    def cleanup_secrets(db_name: str) -> None:
        """
        Securely wipe and remove secret files.
        
        Removes password files from the secrets directory. Handles errors gracefully
        to support cleanup of partially created resources.
        
        Args:
            db_name: Name of the database (container name)
        
        Security:
            - Files are removed (no overwrite needed as they're on tmpfs in production)
            - Validates database name before operation
        """
        # Validate database name - return silently if invalid (idempotent cleanup)
        if not VolumeService.validate_db_name(db_name):
            return
        
        base = Path(VOLUME_BASE_PATH) / db_name / "secrets"
        
        # Remove secret files if they exist
        if base.exists():
            for secret_file in base.glob("*_password"):
                try:
                    if secret_file.is_file():
                        secret_file.unlink()
                except Exception:
                    # Continue cleanup even if individual file fails
                    pass
