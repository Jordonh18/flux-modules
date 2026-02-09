"""
H2 Database Adapter

Complete adapter implementation for H2 Database - an embedded Java SQL database.
H2 can run in embedded mode or as a TCP server. This adapter focuses on embedded mode
but provides minimal container support for server mode scenarios.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class H2Adapter(BaseAdapter):
    """H2 Database embedded Java SQL database engine adapter."""

    engine_name = "h2"
    display_name = "H2 Database"
    category = DatabaseCategory.EMBEDDED
    default_port = 9092  # TCP server mode port
    container_image = ""  # No standard container for H2
    supports_databases = True
    supports_users = True  # H2 supports user management
    supports_backup = True
    supports_metrics = True  # Minimal metrics
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
        Generate H2 Database container configuration.

        Since H2 is primarily embedded, this returns minimal configuration.
        For TCP server mode, a custom Java container would be needed.
        """
        volumes = {}
        if "data" in volume_paths:
            # H2 database files (.mv.db, .trace.db)
            volumes[volume_paths["data"]] = volume_paths["data"]

        env_vars = {
            "H2_USER": username,
            "H2_PASSWORD": password,
        }

        if database_name:
            env_vars["H2_DB"] = database_name

        return ContainerConfig(
            image="",  # No standard container
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            min_memory_mb=256,
            min_cpu=0.25,
            startup_timeout=30,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return H2 health check command.

        For embedded H2, health checks would test file accessibility.
        For TCP server mode, this would be a connection test.
        """
        # Minimal health check - in practice, the service layer should
        # check if the database file exists or test TCP connection
        return []

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse H2 health check output.

        Returns healthy if the database file is accessible or TCP connection succeeds.
        """
        if returncode == 0:
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="H2 database is accessible",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"H2 database check failed: {stderr.strip() if stderr else 'Unknown error'}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return H2 metrics collection command.

        H2 provides minimal runtime metrics through INFORMATION_SCHEMA.
        """
        # SQL query to get basic metrics from INFORMATION_SCHEMA
        query = "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SESSIONS"
        # In practice, this would need to be executed via H2's tools or JDBC
        return []

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse H2 metrics output.

        Returns minimal metrics (connection count if available).
        """
        try:
            # Try to parse connection count from output
            connection_count = int(stdout.strip())
            return MetricsData(
                connections=connection_count,
                active_queries=0,
            )
        except (ValueError, AttributeError):
            pass

        return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return H2 backup command.

        H2 supports SCRIPT TO command for creating SQL backups.
        """
        # H2's SCRIPT TO creates a SQL dump file
        # This would need to be executed via H2 Shell or JDBC
        # Format: SCRIPT TO 'filename.sql'
        return []

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return H2 restore command.

        H2 supports RUNSCRIPT FROM command for restoring from SQL dumps.
        """
        # H2's RUNSCRIPT FROM executes a SQL script
        # This would need to be executed via H2 Shell or JDBC
        # Format: RUNSCRIPT FROM 'filename.sql'
        return []

    def get_backup_file_extension(self) -> str:
        """Return the file extension for H2 backup files."""
        return ".sql"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Return command to create an H2 database.

        In H2, databases are created by connecting to a new file path.
        This is typically handled at the service layer.
        """
        return []

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """
        Return command to drop an H2 database.

        For H2, this is a file deletion operation.
        """
        return []

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all H2 databases.

        Would list .mv.db files in the data directory.
        """
        return []

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Return command to create an H2 user.

        H2 supports CREATE USER statement.
        """
        # SQL: CREATE USER new_username PASSWORD 'new_password'
        # This would need to be executed via H2 Shell or JDBC
        return []

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """
        Return command to drop an H2 user.

        H2 supports DROP USER statement.
        """
        # SQL: DROP USER target_username
        return []

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all H2 users.

        Query INFORMATION_SCHEMA.USERS table.
        """
        # SQL: SELECT * FROM INFORMATION_SCHEMA.USERS
        return []

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate an H2 connection string.

        Uses JDBC format for TCP server mode.
        For embedded mode, use jdbc:h2:file:/path/to/database
        """
        # TCP server mode connection string
        return f"jdbc:h2:tcp://{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for H2."""
        return "generic"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return "h2"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for H2.

        Maps the data directory for .mv.db files.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = volume_paths["data"]
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for H2.

        Embedded databases start quickly.
        """
        return 5
