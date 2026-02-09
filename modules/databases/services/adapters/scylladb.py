"""
ScyllaDB Database Adapter

Complete adapter implementation for ScyllaDB (Cassandra-compatible).
Provides container configuration optimized for containerized environments,
health checks, metrics collection, backup/restore, and keyspace/role management.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class ScyllaDBAdapter(BaseAdapter):
    """ScyllaDB database engine adapter (Cassandra-compatible)."""

    engine_name = "scylladb"
    display_name = "ScyllaDB"
    description = "High-performance Cassandra-compatible wide-column database"
    category = DatabaseCategory.WIDE_COLUMN
    default_port = 9042
    container_image = "docker.io/scylladb/scylla:latest"
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
        Generate ScyllaDB container configuration.

        ScyllaDB is optimized for performance but requires special container
        configuration for single-core/low-memory environments.
        """
        # ScyllaDB configures via command-line args, not env vars
        env_vars = {}

        # Volume mounts - ScyllaDB uses different path than Cassandra
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/scylla:Z"

        # ScyllaDB-specific command for container environments
        # Limits to single CPU and memory to avoid overprovisioning issues
        command = [
            "--smp", "1",  # Single-core mode
            "--memory", "750M",  # Memory limit
            "--overprovisioned", "1",  # Tell Scylla it's in a shared environment
        ]

        # Extra ports for REST API and Prometheus metrics
        extra_ports = {
            10000: 10000,  # REST API
            9180: 9180,    # Prometheus metrics
        }

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            command=command,
            volumes=volumes,
            extra_ports=extra_ports,
            min_memory_mb=1024,  # ScyllaDB is more efficient than Cassandra
            min_cpu=cpu,
            startup_timeout=90,  # Faster than Cassandra but still needs time
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return health check command using cqlsh.

        ScyllaDB is CQL-compatible, so we use the same health check as Cassandra.
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
                    message="ScyllaDB cluster is operational"
                )
        
        # Not healthy
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=stderr or "Failed to connect to ScyllaDB",
            details={"stdout": stdout, "stderr": stderr}
        )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return command to extract metrics from ScyllaDB.

        Uses cqlsh to query system tables (CQL-compatible).
        """
        query = """
        SELECT data_center, rack, status, state, load 
        FROM system.peers_v2 
        LIMIT 10;
        """
        return ["cqlsh", "-e", query]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse ScyllaDB metrics from system queries.

        ScyllaDB provides enhanced metrics via its REST API, but we use
        basic CQL queries for consistency.
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
        Return command to create a ScyllaDB snapshot.

        Uses nodetool snapshot (Cassandra-compatible).
        """
        snapshot_name = f"backup_{database_name}"
        return ["nodetool", "snapshot", "-t", snapshot_name]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return command to restore from a ScyllaDB snapshot.

        Uses sstableloader (Cassandra-compatible).
        """
        return ["sstableloader", "-d", "localhost", restore_path]

    def get_backup_file_extension(self) -> str:
        """ScyllaDB backups are tarball archives."""
        return ".tar.gz"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Create a keyspace in ScyllaDB.

        Uses cqlsh to execute CREATE KEYSPACE command.
        """
        query = f"""
        CREATE KEYSPACE IF NOT EXISTS {db_name}
        WITH REPLICATION = {{'class': 'SimpleStrategy', 'replication_factor': 1}};
        """
        return ["cqlsh", "-e", query]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Drop a ScyllaDB keyspace."""
        query = f"DROP KEYSPACE IF EXISTS {db_name};"
        return ["cqlsh", "-e", query]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all ScyllaDB keyspaces."""
        query = "SELECT keyspace_name FROM system_schema.keyspaces;"
        return ["cqlsh", "-e", query]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Create a ScyllaDB role (user).

        ScyllaDB uses the same role-based authentication as Cassandra.
        """
        query = f"CREATE ROLE IF NOT EXISTS {new_username} WITH PASSWORD = '{new_password}' AND LOGIN = true;"
        return ["cqlsh", "-e", query]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Drop a ScyllaDB role."""
        query = f"DROP ROLE IF EXISTS {target_username};"
        return ["cqlsh", "-e", query]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all ScyllaDB roles."""
        query = "SELECT role FROM system_auth.roles;"
        return ["cqlsh", "-e", query]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate ScyllaDB connection string (Cassandra-compatible)."""
        return f"cassandra://{host}:{port}/{database}"

    def get_log_parser_type(self) -> str:
        """ScyllaDB uses similar log format to Cassandra."""
        return "scylladb"

    def get_startup_probe_delay(self) -> int:
        """ScyllaDB is faster to start than Cassandra but still needs time."""
        return 20
