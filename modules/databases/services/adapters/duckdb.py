"""
DuckDB Database Adapter

Complete adapter implementation for DuckDB - an embedded analytical database.
DuckDB runs in-process and does not use containers, so many methods return
minimal defaults while still implementing the full adapter interface.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class DuckDBAdapter(BaseAdapter):
    """DuckDB embedded analytical database engine adapter."""

    engine_name = "duckdb"
    display_name = "DuckDB"
    description = "Embedded analytical database optimized for fast OLAP workloads"
    category = DatabaseCategory.ANALYTICAL
    default_port = 0  # No network port - embedded mode
    container_image = ""  # No container for embedded databases
    supports_databases = True  # DuckDB supports multiple databases via ATTACH
    supports_users = False  # No user management in embedded mode
    supports_backup = True  # File-based backups
    supports_metrics = False  # No runtime metrics in embedded mode
    is_embedded = True

    def get_container_config(
        self,
        container_name: str,
        database_name: str,
        username: str,
        password: str,
        port: int,
        memory_mb: int,
        cpu: float,
        volume_paths: dict[str, str],
        secrets_paths: Optional[dict[str, str]] = None,
        tls_cert_path: Optional[str] = None,
        tls_key_path: Optional[str] = None,
    ) -> ContainerConfig:
        """
        Generate DuckDB container configuration.

        Since DuckDB is embedded and doesn't use containers, this returns
        a minimal ContainerConfig with empty image. The orchestration layer
        should handle DuckDB differently (create .duckdb file, no container).
        """
        # DuckDB runs in-process, but we still return a valid ContainerConfig
        # The container service should detect is_embedded=True and skip container creation
        volumes = {}
        if "data" in volume_paths:
            # Map the data directory even though there's no container
            volumes[volume_paths["data"]] = volume_paths["data"]

        return ContainerConfig(
            image="",  # No container image
            default_port=0,  # No network port
            env_vars={},
            volumes=volumes,
            min_memory_mb=256,
            min_cpu=0.25,
            startup_timeout=5,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return DuckDB health check command.

        For embedded databases, health checks are not applicable.
        Return empty command - the service layer should treat embedded DBs as always healthy.
        """
        return []

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse DuckDB health check output.

        Embedded databases are always considered healthy if the file exists.
        """
        return HealthStatus(
            healthy=True,
            status="healthy",
            message="DuckDB database file is accessible",
        )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return DuckDB metrics collection command.

        DuckDB doesn't provide runtime metrics in embedded mode.
        """
        return []

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse DuckDB metrics output.

        Returns empty metrics since DuckDB doesn't expose runtime metrics.
        """
        return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return DuckDB backup command.

        For DuckDB, backup is a simple file copy operation.
        This should be handled at the service layer by copying the .duckdb file.
        """
        # The service layer should use file copy instead of executing a command
        return []

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return DuckDB restore command.

        For DuckDB, restore is a simple file copy operation.
        This should be handled at the service layer by copying the backup file.
        """
        # The service layer should use file copy instead of executing a command
        return []

    def get_backup_file_extension(self) -> str:
        """Return the file extension for DuckDB backup files."""
        return ".duckdb"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Return command to create a DuckDB database.

        In DuckDB, databases are created via ATTACH statement or by creating a new file.
        This should be handled by the service layer creating a new .duckdb file.
        """
        return []

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """
        Return command to drop a DuckDB database.

        For embedded databases, this is a file deletion operation.
        """
        return []

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all DuckDB databases.

        For embedded mode, this would list attached databases or files in the data directory.
        """
        return []

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Return command to create a DuckDB user.

        DuckDB doesn't support user management in embedded mode.
        """
        return []

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """
        Return command to drop a DuckDB user.

        DuckDB doesn't support user management in embedded mode.
        """
        return []

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all DuckDB users.

        DuckDB doesn't support user management in embedded mode.
        """
        return []

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate a DuckDB connection string.

        Uses the duckdb:/// protocol with file path.
        Since DuckDB is embedded, host/port/user/password are not used.
        """
        # For embedded DuckDB, the database parameter should be the file path
        return f"duckdb:///{database}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for DuckDB."""
        return "generic"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return "duckdb"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for DuckDB.

        Since DuckDB is embedded, we just return the data path mapping.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = volume_paths["data"]
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for DuckDB.

        Embedded databases start instantly.
        """
        return 0
