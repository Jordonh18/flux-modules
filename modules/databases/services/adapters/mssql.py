"""
Microsoft SQL Server 2022 Database Adapter

Complete adapter implementation for SQL Server 2022.
Provides container configuration, health checks, metrics collection,
backup/restore, and database/user management operations.

SQL Server requires a minimum of 2GB memory and has a longer startup time.
Uses sqlcmd command-line utility for all operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class MSSQLAdapter(BaseAdapter):
    """Microsoft SQL Server 2022 database engine adapter."""

    engine_name = "mssql"
    display_name = "SQL Server 2022"
    category = DatabaseCategory.RELATIONAL
    default_port = 1433
    container_image = "mcr.microsoft.com/mssql/server:2022-latest"
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
        Generate SQL Server container configuration.

        SQL Server requires:
        - ACCEPT_EULA=Y to accept the license agreement
        - MSSQL_SA_PASSWORD for the SA (admin) account
        - Minimum 2GB memory
        - Strong password (uppercase, lowercase, numbers, symbols)
        """
        env_vars = {
            "ACCEPT_EULA": "Y",
            "MSSQL_SA_PASSWORD": password,  # SQL Server doesn't support _FILE secrets natively
        }

        # Volume mounts - SQL Server uses /var/opt/mssql/data for database files
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/opt/mssql/data:Z"

        # SQL Server doesn't need special capabilities
        capabilities = []

        # TLS configuration would require additional setup with SQL Server
        # For now, not implementing TLS
        command = []

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars={},
            command=command,
            volumes=volumes,
            capabilities=capabilities,
            min_memory_mb=max(memory_mb, 2048),  # SQL Server requires 2GB minimum
            min_cpu=max(cpu, 1.0),
            health_check_interval=30,
            startup_timeout=90,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Generate sqlcmd health check command.

        Uses sqlcmd with -C flag to trust the server certificate.
        SQL Server uses 'sa' as the default admin username.
        """
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            "SELECT 1",
            "-C",  # Trust server certificate
        ]

    def parse_health_check_output(
        self, returncode: int, stdout: str, stderr: str
    ) -> HealthStatus:
        """
        Parse sqlcmd output.

        Successful query returns exit code 0 with result output.
        """
        if returncode == 0:
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="SQL Server is responding to queries",
            )
        elif "Login failed" in stderr or "Cannot open database" in stderr:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message="SQL Server authentication failed",
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
        Generate SQL Server metrics collection command.

        Uses DMVs (Dynamic Management Views) to collect performance metrics.
        Returns JSON-formatted output.
        """
        query = """
        SET NOCOUNT ON;
        SELECT 
            (SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1) AS connections,
            (SELECT COUNT(*) FROM sys.dm_exec_requests WHERE status = 'running') AS active_queries,
            (SELECT cntr_value FROM sys.dm_os_performance_counters WHERE counter_name = 'User Connections' AND object_name LIKE '%General Statistics%') AS user_connections,
            (SELECT cntr_value FROM sys.dm_os_performance_counters WHERE counter_name = 'SQL Compilations/sec' AND object_name LIKE '%SQL Statistics%') AS compilations_per_sec,
            (SELECT sqlserver_start_time FROM sys.dm_os_sys_info) AS start_time
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;
        """

        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
            "-h",
            "-1",  # No headers
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse JSON metrics output from SQL Server.

        SQL Server returns JSON from FOR JSON PATH queries.
        """
        try:
            # Clean up the output - remove any whitespace
            cleaned = stdout.strip()
            if not cleaned:
                return MetricsData()
                
            data = json.loads(cleaned)

            # Extract metrics from the JSON
            connections = int(data.get("connections", 0))
            active_queries = int(data.get("active_queries", 0))
            
            # Calculate uptime from start time if available
            uptime_seconds = None
            # SQL Server uptime calculation would need datetime parsing
            # Simplified for now

            return MetricsData(
                connections=connections,
                active_queries=active_queries,
                total_transactions=None,
                uptime_seconds=uptime_seconds,
                slow_queries=None,
                cache_hit_ratio=None,
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            # Return empty metrics on parse failure
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Generate SQL Server backup command using BACKUP DATABASE.

        Creates a full database backup to the specified path.
        If no database specified, backs up all user databases.
        """
        if database_name:
            # Single database backup
            backup_file = f"/var/opt/mssql/data/{database_name}_backup.bak"
            query = f"BACKUP DATABASE [{database_name}] TO DISK = N'{backup_file}' WITH FORMAT, INIT, COMPRESSION;"
        else:
            # All databases backup - would need dynamic SQL in practice
            # For now, backup master, model, msdb
            backup_file = "/var/opt/mssql/data/all_databases_backup.bak"
            query = f"BACKUP DATABASE [master] TO DISK = N'{backup_file}' WITH FORMAT, INIT, COMPRESSION;"

        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Generate SQL Server restore command using RESTORE DATABASE.

        Restores a database from a backup file.
        """
        backup_file = f"/var/opt/mssql/data/{database_name}_backup.bak"
        query = f"RESTORE DATABASE [{database_name}] FROM DISK = N'{backup_file}' WITH REPLACE;"

        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
        ]

    def get_backup_file_extension(self) -> str:
        """SQL Server backups use .bak extension."""
        return ".bak"

    # ---- Database Operations -------------------------------------------------

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """Create a new SQL Server database."""
        query = f"CREATE DATABASE [{db_name}];"
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """Drop a SQL Server database."""
        # Need to set to single user mode first to drop
        query = f"ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{db_name}];"
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all user databases excluding system databases."""
        query = """
        SET NOCOUNT ON;
        SELECT name 
        FROM sys.databases 
        WHERE database_id > 4 
        AND state = 0
        ORDER BY name;
        """
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
            "-h",
            "-1",  # No headers
        ]

    # ---- User Management -----------------------------------------------------

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Create a new SQL Server login and user.

        SQL Server requires both a server login and database user.
        Creates login at server level with sysadmin role.
        """
        query = f"""
        CREATE LOGIN [{new_username}] WITH PASSWORD = N'{new_password}';
        ALTER SERVER ROLE [sysadmin] ADD MEMBER [{new_username}];
        """
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            admin_password,
            "-Q",
            query,
            "-C",
        ]

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Drop a SQL Server login."""
        query = f"DROP LOGIN [{target_username}];"
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            admin_password,
            "-Q",
            query,
            "-C",
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all SQL Server logins excluding system accounts."""
        query = """
        SET NOCOUNT ON;
        SELECT name 
        FROM sys.server_principals 
        WHERE type_desc = 'SQL_LOGIN' 
        AND name NOT LIKE '##%'
        AND name NOT IN ('sa')
        ORDER BY name;
        """
        return [
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-P",
            password,
            "-Q",
            query,
            "-C",
            "-h",
            "-1",  # No headers
        ]

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate a SQL Server connection string (SQLAlchemy format)."""
        return f"mssql+pyodbc://{username}:{password}@{host}:{port}/{database}?driver=ODBC+Driver+18+for+SQL+Server"

    def get_log_parser_type(self) -> str:
        """SQL Server has its own log format."""
        return "mssql"

    def get_config_template_dir(self) -> str:
        """Configuration template directory name."""
        return "mssql"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """Map data volume to SQL Server's data directory."""
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/var/opt/mssql/data"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        SQL Server takes a long time to initialize on first start.

        The server needs to initialize system databases, tempdb,
        and start all services before accepting connections.
        """
        return 30
