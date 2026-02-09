"""
Apache Cassandra 5 Database Adapter

Complete adapter implementation for Apache Cassandra 5.
Provides container configuration, health checks, metrics collection,
backup/restore, and keyspace/role management operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class CassandraAdapter(BaseAdapter):
    """Apache Cassandra 5 database engine adapter."""

    engine_name = "cassandra"
    display_name = "Apache Cassandra 5"
    category = DatabaseCategory.WIDE_COLUMN
    default_port = 9042
    container_image = "docker.io/library/cassandra:5"
    supports_databases = True  # Keyspaces
    supports_users = True  # Roles
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
        Generate Apache Cassandra container configuration.

        Cassandra requires significant memory and takes time to initialize.
        """
        env_vars = {
            "CASSANDRA_CLUSTER_NAME": "flux",
            "CASSANDRA_DC": "datacenter1",
        }

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/cassandra:Z"

        # Extra ports for inter-node communication and Thrift
        extra_ports = {
            7000: 7000,  # Inter-node communication
            9160: 9160,  # Thrift client API (legacy but sometimes used)
        }

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            extra_ports=extra_ports,
            min_memory_mb=2048,  # Cassandra needs substantial memory
            min_cpu=cpu,
            startup_timeout=120,  # Cassandra is slow to start
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return health check command using cqlsh.

        Checks if Cassandra can execute a simple query against system tables.
        """
        return ["cqlsh", "-e", "SELECT now() FROM system.local"]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse cqlsh health check output.

        Looks for successful query execution or connection confirmation.
        """
        if returncode == 0:
            # Check if we got a result or connection message
            if "now()" in stdout or "Connected" in stdout or "UUID" in stdout:
                return HealthStatus(
                    healthy=True,
                    status="healthy",
                    message="Cassandra cluster is operational"
                )
        
        # Not healthy
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=stderr or "Failed to connect to Cassandra",
            details={"stdout": stdout, "stderr": stderr}
        )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return command to extract metrics from Cassandra.

        Uses cqlsh to query system tables for cluster status.
        """
        query = """
        SELECT data_center, rack, status, state, load 
        FROM system.peers_v2 
        LIMIT 10;
        """
        return ["cqlsh", "-e", query]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse Cassandra metrics from system queries.

        Cassandra metrics are complex; this provides basic status.
        """
        metrics = MetricsData()
        
        # Check if node is up
        if "UP" in stdout or "UN" in stdout:
            metrics.custom["cluster_status"] = "UP"
        
        # Try to extract load information if present
        lines = stdout.strip().split('\n')
        for line in lines:
            if "load" in line.lower() or "KB" in line or "MB" in line or "GB" in line:
                metrics.custom["node_load"] = line.strip()
                break
        
        return metrics

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return command to create a Cassandra snapshot.

        Uses nodetool snapshot with a timestamped tag.
        """
        snapshot_name = f"backup_{database_name}"
        return ["nodetool", "snapshot", "-t", snapshot_name]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return command to restore from a Cassandra snapshot.

        Uses sstableloader to restore snapshot data.
        Note: Actual restore is complex and may require manual intervention.
        """
        return ["sstableloader", "-d", "localhost", restore_path]

    def get_backup_file_extension(self) -> str:
        """Cassandra backups are tarball archives."""
        return ".tar.gz"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Create a keyspace in Cassandra.

        Uses cqlsh to execute CREATE KEYSPACE command.
        """
        query = f"""
        CREATE KEYSPACE IF NOT EXISTS {db_name}
        WITH REPLICATION = {{'class': 'SimpleStrategy', 'replication_factor': 1}};
        """
        return ["cqlsh", "-e", query]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Drop a Cassandra keyspace."""
        query = f"DROP KEYSPACE IF EXISTS {db_name};"
        return ["cqlsh", "-e", query]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all Cassandra keyspaces."""
        query = "SELECT keyspace_name FROM system_schema.keyspaces;"
        return ["cqlsh", "-e", query]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Create a Cassandra role (user).

        Cassandra uses roles for authentication.
        """
        query = f"CREATE ROLE IF NOT EXISTS {new_username} WITH PASSWORD = '{new_password}' AND LOGIN = true;"
        return ["cqlsh", "-e", query]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Drop a Cassandra role."""
        query = f"DROP ROLE IF EXISTS {target_username};"
        return ["cqlsh", "-e", query]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all Cassandra roles."""
        query = "SELECT role FROM system_auth.roles;"
        return ["cqlsh", "-e", query]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate Cassandra connection string."""
        return f"cassandra://{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """Cassandra uses its own log format."""
        return "cassandra"

    def get_startup_probe_delay(self) -> int:
        """Cassandra needs extra time before first health check."""
        return 30
