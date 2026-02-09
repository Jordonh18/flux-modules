"""
JanusGraph Database Adapter

Complete adapter implementation for JanusGraph distributed graph database.
Provides container configuration, health checks, metrics collection,
and backup/restore operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class JanusGraphAdapter(BaseAdapter):
    """JanusGraph distributed graph database adapter."""

    engine_name = "janusgraph"
    display_name = "JanusGraph"
    category = DatabaseCategory.GRAPH
    default_port = 8182  # Gremlin Server port
    container_image = "docker.io/janusgraph/janusgraph:latest"
    supports_databases = False  # Single graph per instance
    supports_users = False  # No built-in user management
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
        Generate JanusGraph container configuration.

        JanusGraph is configured via properties files, not environment variables.
        Uses default embedded Cassandra + Berkeley DB backend.
        """
        env_vars = {}
        env_file_vars = {}

        # JanusGraph configuration via environment (limited)
        # Most config is done via properties files

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/janusgraph:Z"

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars=env_file_vars,
            command=[],
            volumes=volumes,
            capabilities=[],
            min_memory_mb=max(memory_mb, 1024),
            min_cpu=max(cpu, 0.5),
            health_check_interval=30,
            startup_timeout=120,  # JanusGraph + backend is slow to start
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return JanusGraph health check command.

        Uses Gremlin query endpoint to verify server is responsive.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:8182?gremlin=g.V().count()"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse JanusGraph health check output.

        The Gremlin query endpoint returns JSON with status 200 when healthy.
        """
        if returncode != 0:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"JanusGraph health check failed: {stderr}",
            )

        try:
            data = json.loads(stdout.strip())
            # Check for successful query response
            if "result" in data and "status" in data:
                status_code = data["status"].get("code", 500)
                if status_code == 200:
                    return HealthStatus(
                        healthy=True,
                        status="healthy",
                        message="JanusGraph is responding to queries",
                    )
                else:
                    return HealthStatus(
                        healthy=False,
                        status="degraded",
                        message=f"JanusGraph returned status {status_code}",
                    )
            else:
                return HealthStatus(
                    healthy=True,
                    status="healthy",
                    message="JanusGraph is responding",
                )
        except json.JSONDecodeError:
            # If we got here with returncode 0, server is up
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="JanusGraph is responding",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return JanusGraph metrics command.

        Uses Gremlin query to get graph statistics.
        """
        # Query for basic graph metrics
        query = "g.V().count()"
        
        return [
            "curl",
            "-sf",
            f"http://localhost:8182?gremlin={query}"
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse JanusGraph metrics output.

        Extracts graph statistics from Gremlin query results.
        """
        try:
            data = json.loads(stdout.strip())
            
            # Extract vertex count if available
            vertex_count = 0
            if "result" in data and "data" in data["result"]:
                result_data = data["result"]["data"]
                if result_data and len(result_data) > 0:
                    vertex_count = result_data[0]

            return MetricsData(
                connections=0,
                active_queries=0,
                custom={
                    "vertex_count": vertex_count,
                    "graph_status": "operational"
                }
            )
        except (json.JSONDecodeError, KeyError, IndexError):
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return JanusGraph backup command.

        Exports graph data via Gremlin I/O to GraphSON format.
        """
        # Use Gremlin to export the graph
        export_script = f"g.io('{backup_path}').with(IO.writer, IO.graphson).write().iterate()"
        
        return [
            "sh",
            "-c",
            f"curl -sf -X POST -H 'Content-Type: application/json' -d '{{\"gremlin\":\"{export_script}\"}}' http://localhost:8182"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return JanusGraph restore command.

        Imports graph data from GraphSON format via Gremlin I/O.
        """
        # Use Gremlin to import the graph
        import_script = f"g.io('{restore_path}').with(IO.reader, IO.graphson).read().iterate()"
        
        return [
            "sh",
            "-c",
            f"curl -sf -X POST -H 'Content-Type: application/json' -d '{{\"gremlin\":\"{import_script}\"}}' http://localhost:8182"
        ]

    def get_backup_file_extension(self) -> str:
        """Return the file extension for JanusGraph backups."""
        return ".json"

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """
        JanusGraph doesn't support multiple databases.
        Returns empty command.
        """
        return []

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """
        JanusGraph doesn't support multiple databases.
        Returns empty command.
        """
        return []

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        JanusGraph doesn't support multiple databases.
        Returns empty command.
        """
        return []

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        JanusGraph doesn't have built-in user management.
        Returns empty command.
        """
        return []

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        JanusGraph doesn't have built-in user management.
        Returns empty command.
        """
        return []

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        JanusGraph doesn't have built-in user management.
        Returns empty command.
        """
        return []

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate a JanusGraph Gremlin connection string.

        Format: ws://host:port/gremlin
        """
        return f"ws://{host}:{port}/gremlin"

    def get_log_parser_type(self) -> str:
        """Return the log format type for JanusGraph."""
        return "generic"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return self.engine_name

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for JanusGraph.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/var/lib/janusgraph:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for JanusGraph.

        JanusGraph with embedded backend is slow to start.
        """
        return 30
