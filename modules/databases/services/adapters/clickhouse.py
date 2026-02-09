"""
ClickHouse Database Adapter

Complete adapter implementation for ClickHouse - a columnar OLAP database.
Provides container configuration, health checks, metrics collection,
backup/restore, and database/user management operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class ClickHouseAdapter(BaseAdapter):
    """ClickHouse columnar OLAP database engine adapter."""

    engine_name = "clickhouse"
    display_name = "ClickHouse"
    description = "Column-oriented database for blazing-fast online analytical queries"
    category = DatabaseCategory.ANALYTICAL
    default_port = 8123  # HTTP interface
    container_image = "docker.io/clickhouse/clickhouse-server:latest"
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
        Generate ClickHouse container configuration.

        Uses environment variables for user/password and database initialization.
        Configures multiple ports (HTTP, native TCP, interserver).
        """
        env_vars = {
            "CLICKHOUSE_USER": username,
            "CLICKHOUSE_PASSWORD": password,
            "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT": "1",
        }

        # Initial database
        if database_name:
            env_vars["CLICKHOUSE_DB"] = database_name

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/clickhouse:Z"
        if "logs" in volume_paths:
            volumes[volume_paths["logs"]] = "/var/log/clickhouse-server:Z"

        # Extra ports for native protocol and interserver communication
        extra_ports = {
            9000: 9000,  # Native TCP protocol
            9009: 9009,  # Interserver HTTP
        }

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            extra_ports=extra_ports,
            min_memory_mb=1024,  # ClickHouse needs more memory for OLAP workloads
            min_cpu=1.0,
            startup_timeout=60,
            health_check_interval=30,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return ClickHouse health check command.

        Uses clickhouse-client to execute a simple SELECT 1 query.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", "SELECT 1"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse ClickHouse health check output.

        Returns healthy if the query executed successfully and returned "1".
        """
        if returncode == 0 and stdout.strip() == "1":
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="ClickHouse is responding to queries",
            )
        elif returncode != 0:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Health check failed: {stderr.strip() if stderr else 'Unknown error'}",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="degraded",
                message=f"Unexpected response: {stdout.strip()}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return ClickHouse metrics collection command.

        Queries system.metrics and system.asynchronous_metrics tables.
        """
        query = """
        SELECT
            (SELECT value FROM system.metrics WHERE metric = 'Query') AS active_queries,
            (SELECT value FROM system.asynchronous_metrics WHERE metric = 'Uptime') AS uptime_seconds,
            (SELECT value FROM system.asynchronous_metrics WHERE metric = 'NumberOfDatabases') AS database_count
        FORMAT JSON
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", query
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse ClickHouse metrics JSON output.

        Extracts active queries, uptime, and other performance metrics.
        """
        try:
            data = json.loads(stdout)
            if "data" in data and len(data["data"]) > 0:
                row = data["data"][0]
                return MetricsData(
                    connections=0,  # ClickHouse doesn't expose connection count easily
                    active_queries=int(row.get("active_queries", 0)),
                    uptime_seconds=int(float(row.get("uptime_seconds", 0))),
                    custom={
                        "database_count": int(row.get("database_count", 0)),
                    }
                )
        except (json.JSONDecodeError, KeyError, ValueError, IndexError):
            pass

        return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return ClickHouse backup command.

        Uses BACKUP DATABASE statement to create a backup to file.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", f"BACKUP DATABASE {database_name} TO File('/tmp/backup')"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return ClickHouse restore command.

        Uses RESTORE DATABASE statement to restore from backup file.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", f"RESTORE DATABASE {database_name} FROM File('/tmp/backup')"
        ]

    def get_backup_file_extension(self) -> str:
        """Return the file extension for ClickHouse backup files."""
        return ".tar"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Return command to create a ClickHouse database.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", f"CREATE DATABASE IF NOT EXISTS {db_name}"
        ]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """
        Return command to drop a ClickHouse database.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", f"DROP DATABASE IF EXISTS {db_name}"
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all ClickHouse databases.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", "SHOW DATABASES FORMAT JSON"
        ]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Return command to create a ClickHouse user.
        """
        return [
            "clickhouse-client",
            "--user", admin_username,
            "--password", admin_password,
            "--query", f"CREATE USER IF NOT EXISTS {new_username} IDENTIFIED BY '{new_password}'"
        ]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """
        Return command to drop a ClickHouse user.
        """
        return [
            "clickhouse-client",
            "--user", admin_username,
            "--password", admin_password,
            "--query", f"DROP USER IF EXISTS {target_username}"
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all ClickHouse users.
        """
        return [
            "clickhouse-client",
            "--user", username,
            "--password", password,
            "--query", "SHOW USERS FORMAT JSON"
        ]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate a ClickHouse connection string.

        Uses the clickhouse:// protocol format.
        """
        return f"clickhouse://{username}:{password}@{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for ClickHouse."""
        return "clickhouse"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return "clickhouse"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for ClickHouse.

        Maps data and logs directories.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/var/lib/clickhouse:Z"
        if "logs" in volume_paths:
            mounts[volume_paths["logs"]] = "/var/log/clickhouse-server:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for ClickHouse.

        ClickHouse needs more time to initialize for OLAP workloads.
        """
        return 10
