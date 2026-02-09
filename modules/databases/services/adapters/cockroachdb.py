"""
CockroachDB Adapter

Complete adapter implementation for CockroachDB, a distributed SQL database
designed for cloud-native applications. This adapter uses single-node mode
with insecure configuration for development/testing environments.

Key characteristics:
- PostgreSQL-compatible SQL dialect
- Distributed architecture (single-node for dev)
- Built-in admin UI on port 8080
- No traditional authentication in insecure mode
- Uses cockroach CLI for operations
"""

import re
import json
from typing import Optional

from .base import (
    BaseAdapter,
    DatabaseCategory,
    ContainerConfig,
    HealthStatus,
    MetricsData,
)


class CockroachDBAdapter(BaseAdapter):
    """CockroachDB distributed SQL database adapter."""

    engine_name = "cockroachdb"
    display_name = "CockroachDB"
    description = "Distributed SQL database built for global scale and resilience"
    category = DatabaseCategory.RELATIONAL
    default_port = 26257
    container_image = "docker.io/cockroachdb/cockroach:latest"
    supports_databases = True
    supports_users = True
    supports_backup = True
    supports_metrics = True
    is_embedded = False

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
        Generate CockroachDB container configuration.

        CockroachDB runs in single-node insecure mode for development.
        Exposes admin UI on port 8080.
        """
        # Single-node insecure mode command
        command = [
            "start-single-node",
            "--insecure",
            "--advertise-addr=localhost"
        ]

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/cockroach/cockroach-data:Z"

        # Extra port for admin UI
        extra_ports = {
            8080: 8080  # Admin UI
        }

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            command=command,
            env_vars={},  # No env vars needed in insecure mode
            volumes=volumes,
            extra_ports=extra_ports,
            min_memory_mb=512,
            min_cpu=cpu,
            startup_timeout=60,
        )

    # ---- Health & Monitoring -------------------------------------------------

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Health check via cockroach sql command.

        Executes a simple SELECT query.
        """
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            "SELECT 1"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse cockroach sql output.

        Success: returncode 0 and output contains result.
        """
        if returncode == 0:
            return HealthStatus(
                healthy=True,
                status="healthy",
                response_time_ms=0,
                message="CockroachDB is running",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Health check failed: {stderr or stdout}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Collect metrics from CockroachDB internal tables.

        Queries crdb_internal.node_runtime_info and other system tables.
        """
        query = (
            "SELECT "
            "(SELECT value FROM crdb_internal.node_metrics WHERE name = 'sql.conns') AS connections, "
            "(SELECT value FROM crdb_internal.node_metrics WHERE name = 'sql.query.count') AS queries "
            "FROM (SELECT 1) AS dummy;"
        )
        
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--format=csv",
            "--execute",
            query
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse CSV metrics output.

        Expected format:
        connections,queries
        5,1234
        """
        lines = stdout.strip().split('\n')
        
        if len(lines) < 2:
            return MetricsData()
        
        # Skip header, parse data line
        data_line = lines[1] if len(lines) > 1 else ""
        parts = data_line.split(',')
        
        if len(parts) >= 2:
            try:
                connections = int(float(parts[0])) if parts[0] else 0
                queries = int(float(parts[1])) if parts[1] else 0
                
                return MetricsData(
                    connections=connections,
                    total_transactions=queries,
                )
            except (ValueError, IndexError):
                pass
        
        return MetricsData()

    # ---- Backup & Restore ----------------------------------------------------

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Backup via CockroachDB BACKUP statement.

        Uses nodelocal storage for backup destination.
        """
        sql = f"BACKUP DATABASE {database_name} INTO 'nodelocal://1/backup';"
        
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            sql
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Restore via CockroachDB RESTORE statement.

        Restores from the latest backup in nodelocal storage.
        """
        sql = f"RESTORE DATABASE {database_name} FROM LATEST IN 'nodelocal://1/backup';"
        
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            sql
        ]

    def get_backup_file_extension(self) -> str:
        """CockroachDB backups are SQL-based."""
        return ".sql"

    # ---- Database Operations -------------------------------------------------

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """Create a new database in CockroachDB."""
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            f"CREATE DATABASE {db_name};"
        ]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Drop a database in CockroachDB."""
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            f"DROP DATABASE {db_name} CASCADE;"
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all databases (excluding system databases)."""
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--format=csv",
            "--execute",
            "SELECT database_name FROM [SHOW DATABASES] WHERE database_name NOT IN ('defaultdb', 'postgres', 'system');"
        ]

    # ---- User Management -----------------------------------------------------

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Create a CockroachDB user.

        In insecure mode, password is optional but we set it for consistency.
        """
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            f"CREATE USER {new_username} WITH PASSWORD '{new_password}';"
        ]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Drop a CockroachDB user."""
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--execute",
            f"DROP USER {target_username};"
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all CockroachDB users."""
        return [
            "cockroach",
            "sql",
            "--insecure",
            "--format=csv",
            "--execute",
            "SELECT username FROM [SHOW USERS];"
        ]

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate CockroachDB connection string.

        CockroachDB is PostgreSQL-compatible, so we use the postgresql:// scheme.
        In insecure mode, sslmode=disable is required.
        """
        return f"postgresql://{username}@{host}:{port}/{database}?sslmode=disable"

    def get_startup_probe_delay(self) -> int:
        """CockroachDB starts relatively quickly."""
        return 15
