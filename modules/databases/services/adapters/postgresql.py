"""
PostgreSQL 16 Database Adapter

Complete adapter implementation for PostgreSQL 16.
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
    BackupInfo,
    DatabaseUser,
    DatabaseInfo,
)


class PostgreSQLAdapter(BaseAdapter):
    """PostgreSQL 16 database engine adapter."""

    engine_name = "postgresql"
    display_name = "PostgreSQL 16"
    description = "Advanced open-source relational database with ACID compliance and extensive SQL support"
    category = DatabaseCategory.RELATIONAL
    default_port = 5432
    container_image = "docker.io/library/postgres:16-alpine"
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
        Generate PostgreSQL container configuration.

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
            # PostgreSQL needs to be told to use the config file
            # We'll handle this via command args

        # TLS certificate mounts
        if tls_cert_path and tls_key_path:
            volumes[tls_cert_path] = "/tls/server.crt:Z,ro"
            volumes[tls_key_path] = "/tls/server.key:Z,ro"

        # Build command with TLS and config if enabled
        command = []
        if "config" in volume_paths:
            command.extend(["-c", "config_file=/etc/postgresql/postgresql.conf"])
        if tls_cert_path and tls_key_path:
            command.extend([
                "-c", "ssl=on",
                "-c", "ssl_cert_file=/tls/server.crt",
                "-c", "ssl_key_file=/tls/server.key",
            ])

        # PostgreSQL needs specific capabilities for user/permission management
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

        pg_isready is included in the PostgreSQL container and checks
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
                message="PostgreSQL server is accepting connections",
            )
        elif returncode == 1:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message="PostgreSQL server is rejecting connections",
            )
        elif returncode == 2:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message="PostgreSQL server is not responding",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unknown",
                message=f"Unexpected health check response: {stdout} {stderr}",
            )

    def get_metrics_command(
        self, database_name: str, username: str, password: str
    ) -> list[str]:
        """
        Generate PostgreSQL metrics collection command.

        Uses pg_stat_activity and pg_stat_database to collect performance metrics.
        Returns JSON-formatted output for easy parsing.
        """
        query = """
        SELECT json_build_object(
            'connections', (SELECT count(*) FROM pg_stat_activity),
            'active_queries', (SELECT count(*) FROM pg_stat_activity WHERE state = 'active'),
            'cache_hit_ratio', (
                SELECT CASE 
                    WHEN (blks_hit + blks_read) > 0 
                    THEN round((blks_hit::numeric / (blks_hit + blks_read)) * 100, 2)
                    ELSE 0
                END
                FROM pg_stat_database 
                WHERE datname = current_database()
            ),
            'total_transactions', (
                SELECT (xact_commit + xact_rollback)
                FROM pg_stat_database 
                WHERE datname = current_database()
            ),
            'uptime_seconds', (
                SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::integer
            )
        ) AS metrics;
        """

        return [
            "psql",
            "-h",
            "localhost",
            "-U",
            username,
            "-d",
            database_name or "postgres",
            "-t",  # Tuples only (no headers)
            "-c",
            query,
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse JSON metrics output from PostgreSQL.
        """
        try:
            data = json.loads(stdout.strip())

            return MetricsData(
                connections=int(data.get("connections", 0)),
                active_queries=int(data.get("active_queries", 0)),
                cache_hit_ratio=float(data.get("cache_hit_ratio", 0.0)) if data.get("cache_hit_ratio") else None,
                total_transactions=int(data.get("total_transactions", 0)) if data.get("total_transactions") else None,
                uptime_seconds=int(data.get("uptime_seconds", 0)) if data.get("uptime_seconds") else None,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Return empty metrics on parse failure
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Generate pg_dump backup command.

        Uses -Fc (custom format) for compressed, restorable backups.
        Backs up the specified database.
        """
        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{password}' pg_dump -h localhost -U {username} -Fc -f {backup_path} {database_name}",
        ]

        return cmd

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Generate pg_restore command.

        Uses -Fc (custom format) to restore from pg_dump custom format backups.
        """
        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{password}' pg_restore -h localhost -U {username} -d {database_name} -c {restore_path}",
        ]

        return cmd

    def get_backup_file_extension(self) -> str:
        """Return the file extension for PostgreSQL backups."""
        return ".dump"

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """
        Generate command to create a new PostgreSQL database.
        """
        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{password}' psql -h localhost -U {username} -c \"CREATE DATABASE {db_name} OWNER {owner};\"",
        ]

        return cmd

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """
        Generate command to drop a PostgreSQL database.
        """
        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{password}' psql -h localhost -U {username} -c \"DROP DATABASE IF EXISTS {db_name};\"",
        ]

        return cmd

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Generate command to list all databases.

        Excludes PostgreSQL system databases (template0, template1).
        """
        query = """
        SELECT json_agg(
            json_build_object(
                'name', datname,
                'owner', pg_catalog.pg_get_userbyid(datdba),
                'size_mb', round(pg_database_size(datname)::numeric / 1048576, 2)
            )
        )
        FROM pg_database
        WHERE datistemplate = false
        AND datname NOT IN ('postgres');
        """

        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{password}' psql -h localhost -U {username} -d postgres -t -c \"{query}\"",
        ]

        return cmd

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Generate command to create a PostgreSQL user/role.
        """
        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{admin_password}' psql -h localhost -U {admin_username} -c \"CREATE USER {new_username} WITH PASSWORD '{new_password}';\"",
        ]

        return cmd

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Generate command to drop a PostgreSQL user/role.
        """
        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{admin_password}' psql -h localhost -U {admin_username} -c \"DROP USER IF EXISTS {target_username};\"",
        ]

        return cmd

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Generate command to list all PostgreSQL users/roles.

        Excludes built-in system roles.
        """
        query = """
        SELECT json_agg(
            json_build_object(
                'username', rolname,
                'has_password', rolpassword IS NOT NULL,
                'can_login', rolcanlogin,
                'is_superuser', rolsuper
            )
        )
        FROM pg_roles
        WHERE rolname NOT LIKE 'pg_%';
        """

        cmd = [
            "sh",
            "-c",
            f"PGPASSWORD='{password}' psql -h localhost -U {username} -d postgres -t -c \"{query}\"",
        ]

        return cmd

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate a PostgreSQL connection string.

        Format: postgresql://username:password@host:port/database
        """
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for PostgreSQL."""
        return "postgresql"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return self.engine_name

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for PostgreSQL.

        Data directory is the primary mount point.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/var/lib/postgresql/data:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for PostgreSQL.

        PostgreSQL typically starts quickly, but we allow 10 seconds
        for initialization and recovery.
        """
        return 10
