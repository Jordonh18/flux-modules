"""
Oracle Database XE 21c Adapter

Complete adapter implementation for Oracle Database Express Edition (XE) 21c.
Oracle XE is a free, feature-limited version of Oracle Database suitable for
development and testing. It has a 2GB RAM minimum and is significantly slower
to start than other database engines.

Key characteristics:
- Very slow startup (60-180 seconds)
- High memory requirements (2GB minimum)
- Uses ORACLE_PWD env var for SYS/SYSTEM password
- Persistent data in /opt/oracle/oradata
- Health checks via sqlplus
- Backup/restore via RMAN (Recovery Manager)
"""

import re
from typing import Optional

from .base import (
    BaseAdapter,
    DatabaseCategory,
    ContainerConfig,
    HealthStatus,
    MetricsData,
)


class OracleAdapter(BaseAdapter):
    """Oracle Database XE 21c adapter."""

    engine_name = "oracle"
    display_name = "Oracle XE 21c"
    description = "Enterprise relational database with comprehensive SQL and PL/SQL support"
    category = DatabaseCategory.RELATIONAL
    default_port = 1521
    container_image = "container-registry.oracle.com/database/express:21.3.0-xe"
    supports_databases = True  # Oracle has pluggable databases (PDBs)
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
        Generate Oracle XE container configuration.

        Oracle XE uses ORACLE_PWD environment variable for the SYS/SYSTEM password.
        Data persists in /opt/oracle/oradata.
        """
        env_vars = {}
        
        if secrets_paths and "root_password" in secrets_paths:
            # Use Docker secrets pattern with _FILE suffix
            env_vars = {
                "ORACLE_PWD_FILE": "/secrets/root_password",
            }
        else:
            env_vars = {
                "ORACLE_PWD": password,
            }

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/opt/oracle/oradata:Z"

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            min_memory_mb=2048,  # Oracle XE requires minimum 2GB RAM
            min_cpu=cpu,
            startup_timeout=180,  # Oracle is VERY slow to start
        )

    # ---- Health & Monitoring -------------------------------------------------

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Health check via sqlplus.

        Connects as SYS user (DBA) and executes a simple query.
        """
        return [
            "sh",
            "-c",
            f"echo 'SELECT 1 FROM DUAL;' | sqlplus -s sys/{password}@localhost:1521/XE as sysdba"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse sqlplus output.

        Success: returncode 0 and output contains the result "1"
        """
        if returncode == 0 and "1" in stdout:
            return HealthStatus(
                healthy=True,
                status="healthy",
                response_time_ms=0,
                message="Oracle XE is running",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Health check failed: {stderr or stdout}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Collect metrics via sqlplus queries.

        Queries v$session for connection count and v$sysstat for statistics.
        """
        query = (
            "SELECT "
            "(SELECT COUNT(*) FROM v\\$session) AS sessions, "
            "(SELECT value FROM v\\$sysstat WHERE name = 'user commits') AS commits, "
            "(SELECT value FROM v\\$sysstat WHERE name = 'physical reads') AS reads "
            "FROM DUAL;"
        )
        
        return [
            "sh",
            "-c",
            f"echo \"{query}\" | sqlplus -s sys/{password}@localhost:1521/XE as sysdba"
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse sqlplus metrics output.

        Expected format (space-separated):
        SESSIONS COMMITS READS
        -------- ------- -----
        15       1234    5678
        """
        lines = stdout.strip().split('\n')
        
        # Find the data line (skip headers and separators)
        data_line = None
        for line in lines:
            if line.strip() and not line.startswith('-') and not 'SESSIONS' in line:
                data_line = line
                break
        
        if not data_line:
            return MetricsData()
        
        parts = data_line.split()
        if len(parts) >= 3:
            try:
                sessions = int(parts[0])
                commits = int(parts[1])
                reads = int(parts[2])
                
                return MetricsData(
                    connections=sessions,
                    total_transactions=commits,
                    custom={
                        "physical_reads": reads,
                    }
                )
            except (ValueError, IndexError):
                pass
        
        return MetricsData()

    # ---- Backup & Restore ----------------------------------------------------

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Backup via RMAN (Recovery Manager).

        Creates a full database backup to the specified path.
        """
        rman_script = (
            f"BACKUP DATABASE FORMAT '{backup_path}/%U' TAG 'full_backup'; "
            "EXIT;"
        )
        
        return [
            "sh",
            "-c",
            f"echo \"{rman_script}\" | rman target sys/{password}@XE"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Restore via RMAN.

        Restores the database from the specified backup path.
        """
        rman_script = (
            "SHUTDOWN IMMEDIATE; "
            "STARTUP MOUNT; "
            f"RESTORE DATABASE FROM '{restore_path}'; "
            "RECOVER DATABASE; "
            "ALTER DATABASE OPEN; "
            "EXIT;"
        )
        
        return [
            "sh",
            "-c",
            f"echo \"{rman_script}\" | rman target sys/{password}@XE"
        ]

    def get_backup_file_extension(self) -> str:
        """Oracle RMAN backups use .dmp extension."""
        return ".dmp"

    # ---- Database Operations -------------------------------------------------

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Create a pluggable database (PDB) in Oracle.

        Oracle XE supports pluggable databases starting with 21c.
        """
        sql = f"CREATE PLUGGABLE DATABASE {db_name} ADMIN USER {owner} IDENTIFIED BY {password};"
        
        return [
            "sh",
            "-c",
            f"echo \"{sql}\" | sqlplus -s sys/{password}@localhost:1521/XE as sysdba"
        ]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Drop a pluggable database."""
        sql = f"DROP PLUGGABLE DATABASE {db_name} INCLUDING DATAFILES;"
        
        return [
            "sh",
            "-c",
            f"echo \"{sql}\" | sqlplus -s sys/{password}@localhost:1521/XE as sysdba"
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all pluggable databases."""
        sql = "SELECT name FROM v\\$pdbs WHERE name != 'PDB\\$SEED';"
        
        return [
            "sh",
            "-c",
            f"echo \"{sql}\" | sqlplus -s sys/{password}@localhost:1521/XE as sysdba"
        ]

    # ---- User Management -----------------------------------------------------

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Create an Oracle user."""
        sql = (
            f"CREATE USER {new_username} IDENTIFIED BY {new_password}; "
            f"GRANT CONNECT, RESOURCE TO {new_username};"
        )
        
        return [
            "sh",
            "-c",
            f"echo \"{sql}\" | sqlplus -s sys/{admin_password}@localhost:1521/XE as sysdba"
        ]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Drop an Oracle user."""
        sql = f"DROP USER {target_username} CASCADE;"
        
        return [
            "sh",
            "-c",
            f"echo \"{sql}\" | sqlplus -s sys/{admin_password}@localhost:1521/XE as sysdba"
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all Oracle users (excluding system users)."""
        sql = (
            "SELECT username FROM dba_users "
            "WHERE username NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DIP', 'ORACLE_OCM', 'DBSNMP', 'APPQOSSYS', 'DBSFWUSER', 'GGSYS', 'GSMADMIN_INTERNAL', 'SYSBACKUP', 'SYSDG', 'SYSKM', 'SYSRAC', 'AUDSYS', 'DV\\$MONITOR', 'DV\\$OWNER', 'DV\\$ACCTMGR', 'AWRUSER', 'SYSRAC', 'REMOTE_SCHEDULER_AGENT', 'OJVMSYS', 'XDB', 'ANONYMOUS', 'CTXSYS', 'LBACSYS', 'EXFSYS', 'DVSYS', 'WMSYS', 'MDDATA', 'MDSYS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'ORDDATA', 'ORDPLUGINS', 'ORDSYS', 'FLOWS_FILES', 'APEX_PUBLIC_USER', 'APEX_REST_PUBLIC_USER', 'APEX_LISTENER', 'ORDS_PUBLIC_USER', 'DVF', 'DVSYS');"
        )
        
        return [
            "sh",
            "-c",
            f"echo \"{sql}\" | sqlplus -s sys/{password}@localhost:1521/XE as sysdba"
        ]

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate Oracle connection string (SQLAlchemy format)."""
        return f"oracle+cx_oracle://{username}:{password}@{host}:{port}/XE"

    def get_startup_probe_delay(self) -> int:
        """Oracle XE needs significant time before first health check."""
        return 60
