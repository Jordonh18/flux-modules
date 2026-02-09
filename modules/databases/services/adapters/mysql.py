"""
MySQL 8.0 Database Adapter

Complete adapter implementation for MySQL 8.0 Community Edition.
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


class MySQLAdapter(BaseAdapter):
    """MySQL 8.0 database engine adapter."""

    engine_name = "mysql"
    display_name = "MySQL 8.0"
    description = "Popular open-source relational database known for reliability and ease of use"
    category = DatabaseCategory.RELATIONAL
    default_port = 3306
    container_image = "docker.io/library/mysql:8.0"
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
        Generate MySQL container configuration.

        Uses Docker secrets pattern (_FILE suffix) when secrets_paths provided,
        otherwise falls back to plaintext environment variables.
        """
        env_vars = {}
        env_file_vars = {}

        # Root password configuration (required)
        if secrets_paths and "root_password" in secrets_paths:
            env_file_vars["MYSQL_ROOT_PASSWORD"] = secrets_paths["root_password"]
        else:
            env_vars["MYSQL_ROOT_PASSWORD"] = password

        # Application user configuration
        if username != "root":
            env_vars["MYSQL_USER"] = username
            if secrets_paths and "user_password" in secrets_paths:
                env_file_vars["MYSQL_PASSWORD"] = secrets_paths["user_password"]
            else:
                env_vars["MYSQL_PASSWORD"] = password

        # Initial database
        if database_name:
            env_vars["MYSQL_DATABASE"] = database_name

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/mysql:Z"

        # Configuration file mount
        if "config" in volume_paths:
            volumes[volume_paths["config"]] = "/etc/mysql/conf.d/flux.cnf:Z,ro"

        # TLS certificate mounts
        if tls_cert_path and tls_key_path:
            volumes[tls_cert_path] = "/tls/server.crt:Z,ro"
            volumes[tls_key_path] = "/tls/server.key:Z,ro"

        # Build command with TLS if enabled
        command = []
        if tls_cert_path and tls_key_path:
            command = [
                "--ssl-cert=/tls/server.crt",
                "--ssl-key=/tls/server.key",
            ]

        # MySQL needs specific capabilities for user management
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
        Generate mysqladmin ping command for health check.

        Uses mysqladmin utility which is included in the MySQL container.
        """
        return [
            "mysqladmin",
            "ping",
            "-h",
            "localhost",
            "-u",
            username,
            f"-p{password}",
        ]

    def parse_health_check_output(
        self, returncode: int, stdout: str, stderr: str
    ) -> HealthStatus:
        """
        Parse mysqladmin ping output.

        mysqladmin ping returns "mysqld is alive" when healthy.
        """
        if returncode == 0 and "mysqld is alive" in stdout:
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="MySQL server is responding to ping",
            )
        elif returncode != 0 and "Can't connect to MySQL server" in stderr:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message="MySQL server is not accepting connections",
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
        Generate MySQL metrics collection command.

        Uses SHOW GLOBAL STATUS to collect performance metrics.
        Returns JSON-formatted output for easy parsing.
        """
        query = """
        SELECT JSON_OBJECT(
            'connections', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Threads_connected'),
            'active_queries', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Threads_running'),
            'total_transactions', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Questions'),
            'uptime_seconds', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Uptime'),
            'slow_queries', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Slow_queries'),
            'innodb_buffer_pool_reads', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_reads'),
            'innodb_buffer_pool_read_requests', (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_read_requests')
        ) AS metrics;
        """

        return [
            "mysql",
            "-h",
            "localhost",
            "-u",
            username,
            f"-p{password}",
            "-N",  # No column names
            "-e",
            query,
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse JSON metrics output from MySQL.

        Calculates cache hit ratio from InnoDB buffer pool statistics.
        """
        try:
            data = json.loads(stdout.strip())

            # Calculate InnoDB buffer pool cache hit ratio
            buffer_reads = int(data.get("innodb_buffer_pool_reads", 0))
            buffer_requests = int(data.get("innodb_buffer_pool_read_requests", 1))
            
            cache_hit_ratio = None
            if buffer_requests > 0:
                cache_hit_ratio = (
                    (buffer_requests - buffer_reads) / buffer_requests * 100
                )

            return MetricsData(
                connections=int(data.get("connections", 0)),
                active_queries=int(data.get("active_queries", 0)),
                total_transactions=int(data.get("total_transactions", 0)),
                uptime_seconds=int(data.get("uptime_seconds", 0)),
                slow_queries=int(data.get("slow_queries", 0)),
                cache_hit_ratio=cache_hit_ratio,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Return empty metrics on parse failure
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Generate mysqldump backup command.

        Uses --single-transaction for consistent InnoDB backups without locking.
        Backs up all databases unless a specific database is requested.
        """
        cmd = [
            "mysqldump",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--events",
            "-u",
            username,
            f"-p{password}",
        ]

        if database_name:
            cmd.extend(["--databases", database_name])
        else:
            cmd.append("--all-databases")

        return cmd

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Generate MySQL restore command.

        Pipes the backup file into the mysql CLI client.
        """
        cmd = [
            "mysql",
            "-u",
            username,
            f"-p{password}",
        ]

        if database_name:
            cmd.append(database_name)

        return cmd

    def get_backup_file_extension(self) -> str:
        """MySQL backups are SQL files."""
        return ".sql"

    # ---- Database Operations -------------------------------------------------

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """Create a new MySQL database with UTF-8 encoding."""
        return [
            "mysql",
            "-u",
            username,
            f"-p{password}",
            "-e",
            f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """Drop a MySQL database."""
        return [
            "mysql",
            "-u",
            username,
            f"-p{password}",
            "-e",
            f"DROP DATABASE IF EXISTS `{db_name}`;",
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all databases excluding system databases."""
        query = """
        SELECT SCHEMA_NAME 
        FROM information_schema.SCHEMATA 
        WHERE SCHEMA_NAME NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        ORDER BY SCHEMA_NAME;
        """
        return [
            "mysql",
            "-u",
            username,
            f"-p{password}",
            "-N",  # No column names
            "-e",
            query,
        ]

    # ---- User Management -----------------------------------------------------

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Create a new MySQL user with full privileges.

        Creates user with wildcard host (%) to allow connections from any host.
        """
        query = f"""
        CREATE USER IF NOT EXISTS '{new_username}'@'%' IDENTIFIED BY '{new_password}';
        GRANT ALL PRIVILEGES ON *.* TO '{new_username}'@'%' WITH GRANT OPTION;
        FLUSH PRIVILEGES;
        """
        return [
            "mysql",
            "-u",
            admin_username,
            f"-p{admin_password}",
            "-e",
            query,
        ]

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Drop a MySQL user."""
        query = f"DROP USER IF EXISTS '{target_username}'@'%'; FLUSH PRIVILEGES;"
        return [
            "mysql",
            "-u",
            admin_username,
            f"-p{admin_password}",
            "-e",
            query,
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all MySQL users excluding system users."""
        query = """
        SELECT DISTINCT User 
        FROM mysql.user 
        WHERE User NOT IN ('mysql.sys', 'mysql.session', 'mysql.infoschema', 'root')
        AND User != ''
        ORDER BY User;
        """
        return [
            "mysql",
            "-u",
            username,
            f"-p{password}",
            "-N",  # No column names
            "-e",
            query,
        ]

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate a MySQL connection URI."""
        return f"mysql://{username}:{password}@{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """MySQL uses its own log format."""
        return "mysql"

    def get_config_template_dir(self) -> str:
        """Configuration template directory name."""
        return "mysql"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """Map data volume to MySQL's data directory."""
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/var/lib/mysql"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        MySQL takes longer to initialize on first start.

        The server needs time to initialize the data directory,
        create system tables, and start accepting connections.
        """
        return 15
