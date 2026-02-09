"""
TimescaleDB Database Adapter

Complete adapter implementation for TimescaleDB (PostgreSQL extension for time-series data).
Provides container configuration, health checks, metrics collection,
backup/restore, and database/user management operations.
"""

import json
from typing import Optional

from .base import (
    BaseAdapter,
    DatabaseCategory,
    ContainerConfig,
    HealthStatus,
    MetricsData,
)


class TimescaleDBAdapter(BaseAdapter):
    """TimescaleDB database engine adapter."""

    engine_name = "timescaledb"
    display_name = "TimescaleDB"
    category = DatabaseCategory.TIME_SERIES
    default_port = 5432
    container_image = "docker.io/timescale/timescaledb:latest-pg16"
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
        Generate TimescaleDB container configuration.

        Uses Docker secrets pattern (_FILE suffix) when secrets_paths provided,
        otherwise falls back to plaintext environment variables.
        """
        env_vars = {}
        env_file_vars = {}

        # User configuration
        env_vars["POSTGRES_USER"] = username

        # Password configuration
        if secrets_paths and "user_password" in secrets_paths:
            env_file_vars["POSTGRES_PASSWORD"] = secrets_paths["user_password"]
        else:
            env_vars["POSTGRES_PASSWORD"] = password

        # Initial database
        if database_name:
            env_vars["POSTGRES_DB"] = database_name

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/postgresql/data:Z"

        # Configuration file mount
        if "config" in volume_paths:
            volumes[volume_paths["config"]] = "/etc/postgresql/postgresql.conf:Z,ro"

        # TLS certificate mounts
        if tls_cert_path and tls_key_path:
            volumes[tls_cert_path] = "/tls/server.crt:Z,ro"
            volumes[tls_key_path] = "/tls/server.key:Z,ro"

        # Build command with TimescaleDB extension preload
        command = ["-c", "shared_preload_libraries=timescaledb"]

        # Add config file if provided
        if "config" in volume_paths:
            command.extend(["-c", "config_file=/etc/postgresql/postgresql.conf"])

        # Add TLS if enabled
        if tls_cert_path and tls_key_path:
            command.extend([
                "-c", "ssl=on",
                "-c", "ssl_cert_file=/tls/server.crt",
                "-c", "ssl_key_file=/tls/server.key",
            ])

        # PostgreSQL/TimescaleDB needs specific capabilities for user/permission management
        capabilities = [
            "SETGID",
            "SETUID",
            "CHOWN",
            "DAC_OVERRIDE",
        ]

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars=env_file_vars,
            command=command,
            volumes=volumes,
            capabilities=capabilities,
            min_memory_mb=max(memory_mb, 512),
            min_cpu=max(cpu, 0.5),
            health_check_interval=30,
            startup_timeout=90,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Generate pg_isready command for health check.

        pg_isready is included in the TimescaleDB container and checks
        if the server is ready to accept connections.
        """
        return [
            "pg_isready",
            "-h",
            "localhost",
            "-U",
            username,
        ]

    def parse_health_check_output(
        self, returncode: int, stdout: str, stderr: str
    ) -> HealthStatus:
        """
        Parse pg_isready output.

        pg_isready returns exit code 0 and "accepting connections" when healthy.
        """
        if returncode == 0 and "accepting connections" in stdout:
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="TimescaleDB server is accepting connections",
            )
        elif returncode == 1:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message="TimescaleDB server is rejecting connections",
                details={"stderr": stderr},
            )
        elif returncode == 2:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message="TimescaleDB server connection issue",
                details={"stderr": stderr},
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unknown",
                message=f"Unknown health check state (exit {returncode})",
                details={"stdout": stdout, "stderr": stderr},
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Generate psql command to collect TimescaleDB-specific metrics.

        Combines standard PostgreSQL metrics with TimescaleDB extension metrics.
        """
        query = """
        SELECT json_build_object(
            'connections', (SELECT count(*) FROM pg_stat_activity),
            'active_queries', (SELECT count(*) FROM pg_stat_activity WHERE state = 'active'),
            'cache_hit_ratio', ROUND((sum(blks_hit) / NULLIF(sum(blks_hit + blks_read), 0) * 100)::numeric, 2)
                FROM pg_stat_database,
            'uptime_seconds', EXTRACT(EPOCH FROM (NOW() - pg_postmaster_start_time()))::bigint,
            'total_transactions', (SELECT sum(xact_commit + xact_rollback) FROM pg_stat_database),
            'slow_queries', (SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - interval '5 seconds'),
            'storage_used_mb', ROUND((pg_database_size(current_database()) / 1048576.0)::numeric, 2),
            'hypertables_count', (SELECT count(*) FROM timescaledb_information.hypertables),
            'chunks_count', (SELECT count(*) FROM timescaledb_information.chunks),
            'compression_enabled', (SELECT count(*) > 0 FROM timescaledb_information.compression_settings)
        )::text;
        """
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            username,
            "-d",
            database_name,
            "-t",
            "-A",
            "-c",
            query,
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse JSON metrics output from psql query.

        Returns MetricsData with TimescaleDB-specific custom fields.
        """
        try:
            data = json.loads(stdout.strip())
            return MetricsData(
                connections=int(data.get("connections", 0)),
                active_queries=int(data.get("active_queries", 0)),
                cache_hit_ratio=float(data.get("cache_hit_ratio", 0.0)) if data.get("cache_hit_ratio") else None,
                uptime_seconds=int(data.get("uptime_seconds", 0)) if data.get("uptime_seconds") else None,
                total_transactions=int(data.get("total_transactions", 0)) if data.get("total_transactions") else None,
                slow_queries=int(data.get("slow_queries", 0)),
                storage_used_mb=float(data.get("storage_used_mb", 0.0)) if data.get("storage_used_mb") else None,
                custom={
                    "hypertables_count": int(data.get("hypertables_count", 0)),
                    "chunks_count": int(data.get("chunks_count", 0)),
                    "compression_enabled": bool(data.get("compression_enabled", False)),
                },
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Return empty metrics on parse failure
            return MetricsData(
                custom={"parse_error": str(e)}
            )

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Generate pg_dump command for backup.

        Uses custom format (-Fc) for efficient compression and parallel restore.
        """
        return [
            "pg_dump",
            "-h",
            "localhost",
            "-U",
            username,
            "-d",
            database_name,
            "-Fc",
            "-f",
            backup_path,
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Generate pg_restore command for restore.

        Restores from custom format dump created by pg_dump.
        """
        return [
            "pg_restore",
            "-h",
            "localhost",
            "-U",
            username,
            "-d",
            database_name,
            "-c",  # Clean (drop) database objects before recreating
            restore_path,
        ]

    def get_backup_file_extension(self) -> str:
        """Return .dump for PostgreSQL custom format backups."""
        return ".dump"

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """Generate psql command to create a new database."""
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            username,
            "-c",
            f"CREATE DATABASE {db_name} OWNER {owner};",
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """Generate psql command to drop a database."""
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            username,
            "-c",
            f"DROP DATABASE IF EXISTS {db_name};",
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """Generate psql command to list all databases."""
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            username,
            "-t",
            "-A",
            "-c",
            "SELECT datname FROM pg_database WHERE datistemplate = false;",
        ]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Generate psql command to create a new user."""
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            admin_username,
            "-c",
            f"CREATE USER {new_username} WITH PASSWORD '{new_password}';",
        ]

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Generate psql command to drop a user."""
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            admin_username,
            "-c",
            f"DROP USER IF EXISTS {target_username};",
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """Generate psql command to list all users."""
        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            username,
            "-t",
            "-A",
            "-c",
            "SELECT usename FROM pg_user;",
        ]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for structured log parsing."""
        return "postgresql"

    def get_config_template_dir(self) -> str:
        """Return the subdirectory name under config_templates/ for this engine."""
        return "postgresql"  # TimescaleDB uses PostgreSQL config format

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """Return host_path -> container_path mappings for data persistence."""
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/var/lib/postgresql/data:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """Seconds to wait after container start before first health check."""
        return 10
