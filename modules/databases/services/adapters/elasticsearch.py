"""
Elasticsearch 8.11 Database Adapter

Complete adapter implementation for Elasticsearch 8.11.
Provides container configuration, health checks, metrics collection,
backup/restore, and index management operations.

Note: User management is handled by X-Pack security in production.
This adapter runs with security disabled for development/testing.
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


class ElasticsearchAdapter(BaseAdapter):
    """Elasticsearch 8.11 search engine adapter."""

    engine_name = "elasticsearch"
    display_name = "Elasticsearch 8.11"
    description = "Distributed search and analytics engine for all types of data"
    category = DatabaseCategory.SEARCH
    default_port = 9200
    container_image = "docker.elastic.co/elasticsearch/elasticsearch:8.11.0"
    supports_databases = True  # Elasticsearch has indices
    supports_users = False  # User management via X-Pack (not implemented for dev mode)
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
        Generate Elasticsearch container configuration.

        Elasticsearch requires:
        - Single-node discovery mode for standalone instances
        - JVM heap configuration (half of available memory)
        - Security disabled for development (or enabled with TLS)
        - Significant startup time (120 seconds)
        """
        env_vars = {}
        env_file_vars = {}

        # Single-node discovery (required for standalone instances)
        env_vars["discovery.type"] = "single-node"

        # Security configuration
        # In development mode, disable security for simplicity
        # In production, enable with TLS
        if tls_cert_path and tls_key_path:
            env_vars["xpack.security.enabled"] = "true"
            env_vars["xpack.security.http.ssl.enabled"] = "true"
            env_vars["xpack.security.http.ssl.certificate"] = "/tls/server.crt"
            env_vars["xpack.security.http.ssl.key"] = "/tls/server.key"
        else:
            env_vars["xpack.security.enabled"] = "false"

        # Elastic superuser password
        if secrets_paths and "elastic_password" in secrets_paths:
            env_file_vars["ELASTIC_PASSWORD"] = secrets_paths["elastic_password"]
        else:
            env_vars["ELASTIC_PASSWORD"] = password

        # JVM heap configuration
        # Elasticsearch requires heap to be set explicitly
        # Best practice: half of available container memory
        heap_mb = max(memory_mb // 2, 512)  # Minimum 512MB heap
        env_vars["ES_JAVA_OPTS"] = f"-Xms{heap_mb}m -Xmx{heap_mb}m"

        # Disable bootstrap checks for development
        env_vars["bootstrap.memory_lock"] = "false"

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/usr/share/elasticsearch/data:Z"

        # Configuration file mount (optional)
        if "config" in volume_paths:
            volumes[volume_paths["config"]] = "/usr/share/elasticsearch/config/elasticsearch.yml:Z,ro"

        # TLS certificate mounts
        if tls_cert_path and tls_key_path:
            volumes[tls_cert_path] = "/tls/server.crt:Z,ro"
            volumes[tls_key_path] = "/tls/server.key:Z,ro"

        # Extra ports for cluster communication
        extra_ports = {
            9300: 9300,  # Transport port for node-to-node communication
        }

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars=env_file_vars,
            command=[],  # Use default Elasticsearch command
            volumes=volumes,
            capabilities=[],  # Elasticsearch doesn't require special capabilities
            extra_ports=extra_ports,
            min_memory_mb=max(memory_mb, 2048),  # Elasticsearch needs significant memory
            min_cpu=max(cpu, 1.0),
            health_check_interval=30,
            startup_timeout=120,  # Elasticsearch is slow to start (JVM initialization)
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Generate Elasticsearch health check command.

        Uses the cluster health API to verify the cluster is operational.
        The -sf flag makes curl silent but show errors, and fail on HTTP errors.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:9200/_cluster/health",
        ]

    def parse_health_check_output(
        self, returncode: int, stdout: str, stderr: str
    ) -> HealthStatus:
        """
        Parse Elasticsearch cluster health output.

        The cluster health API returns JSON with a 'status' field:
        - green: All primary and replica shards are active
        - yellow: All primary shards are active, but some replicas are not
        - red: Some primary shards are not active

        For single-node instances, yellow is expected and acceptable.
        """
        if returncode != 0:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Elasticsearch health check failed: {stderr}",
            )

        try:
            data = json.loads(stdout.strip())
            cluster_status = data.get("status", "unknown")
            cluster_name = data.get("cluster_name", "unknown")
            number_of_nodes = data.get("number_of_nodes", 0)

            # Green and yellow are both considered healthy
            # Yellow is normal for single-node clusters (no replicas)
            if cluster_status in ("green", "yellow"):
                return HealthStatus(
                    healthy=True,
                    status="healthy",
                    message=f"Cluster '{cluster_name}' is {cluster_status} with {number_of_nodes} node(s)",
                    details={
                        "cluster_status": cluster_status,
                        "cluster_name": cluster_name,
                        "number_of_nodes": number_of_nodes,
                    },
                )
            elif cluster_status == "red":
                return HealthStatus(
                    healthy=False,
                    status="unhealthy",
                    message=f"Cluster '{cluster_name}' is red (primary shards unavailable)",
                    details={"cluster_status": cluster_status},
                )
            else:
                return HealthStatus(
                    healthy=False,
                    status="unknown",
                    message=f"Unknown cluster status: {cluster_status}",
                )
        except (json.JSONDecodeError, KeyError) as e:
            return HealthStatus(
                healthy=False,
                status="unknown",
                message=f"Failed to parse health check response: {e}",
            )

    def get_metrics_command(
        self, database_name: str, username: str, password: str
    ) -> list[str]:
        """
        Generate Elasticsearch metrics collection command.

        Uses the cluster stats API to collect comprehensive cluster metrics.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:9200/_cluster/stats",
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse Elasticsearch cluster stats JSON output into MetricsData.

        Extracts:
        - Index count and document count
        - Storage usage
        - JVM memory usage
        - Open file descriptors
        """
        try:
            data = json.loads(stdout.strip())

            # Extract indices statistics
            indices = data.get("indices", {})
            index_count = indices.get("count", 0)
            docs_count = indices.get("docs", {}).get("count", 0)
            store_size_bytes = indices.get("store", {}).get("size_in_bytes", 0)

            # Extract node statistics
            nodes = data.get("nodes", {})
            process = nodes.get("process", {})
            open_file_descriptors = process.get("open_file_descriptors", {})
            avg_open_fds = open_file_descriptors.get("avg", 0)

            # JVM memory statistics
            jvm = nodes.get("jvm", {})
            mem = jvm.get("mem", {})
            heap_used_bytes = mem.get("heap_used_in_bytes", 0)
            heap_max_bytes = mem.get("heap_max_in_bytes", 1)

            # Calculate heap usage percentage as cache hit ratio proxy
            heap_usage_pct = (heap_used_bytes / heap_max_bytes * 100) if heap_max_bytes > 0 else 0

            return MetricsData(
                connections=0,  # Elasticsearch doesn't expose connection count easily
                active_queries=0,  # Would require tasks API
                uptime_seconds=nodes.get("jvm", {}).get("max_uptime_in_millis", 0) // 1000,
                storage_used_mb=store_size_bytes / (1024 * 1024),
                custom={
                    "index_count": index_count,
                    "document_count": docs_count,
                    "open_file_descriptors": int(avg_open_fds),
                    "heap_used_mb": heap_used_bytes / (1024 * 1024),
                    "heap_max_mb": heap_max_bytes / (1024 * 1024),
                    "heap_usage_percent": round(heap_usage_pct, 2),
                },
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Return empty metrics on parse failure
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Generate Elasticsearch snapshot backup command.

        This is a simplified implementation using the snapshot API.
        In production, you would:
        1. Register a snapshot repository
        2. Create a snapshot
        3. Export snapshot metadata

        For now, we use a simple curl command to trigger a snapshot.
        """
        # Simplified backup: create a snapshot named by timestamp
        snapshot_name = f"snapshot_{database_name or 'all'}"
        return [
            "curl",
            "-sf",
            "-X",
            "PUT",
            f"http://localhost:9200/_snapshot/backup/{snapshot_name}",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"indices": database_name if database_name else "*"}),
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Generate Elasticsearch snapshot restore command.

        This is a simplified implementation.
        In production, you would restore from a registered snapshot repository.
        """
        snapshot_name = f"snapshot_{database_name or 'all'}"
        return [
            "curl",
            "-sf",
            "-X",
            "POST",
            f"http://localhost:9200/_snapshot/backup/{snapshot_name}/_restore",
        ]

    def get_backup_file_extension(self) -> str:
        """Elasticsearch snapshots are stored as JSON metadata + binary data."""
        return ".json"

    # ---- Index (Database) Operations ----------------------------------------

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """
        Create an Elasticsearch index.

        In Elasticsearch, indices are equivalent to databases.
        """
        return [
            "curl",
            "-sf",
            "-X",
            "PUT",
            f"http://localhost:9200/{db_name}",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,  # Single-node: no replicas
                }
            }),
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """Delete an Elasticsearch index."""
        return [
            "curl",
            "-sf",
            "-X",
            "DELETE",
            f"http://localhost:9200/{db_name}",
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        List all Elasticsearch indices.

        Uses the _cat/indices API with JSON format.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:9200/_cat/indices?format=json",
        ]

    # ---- User Management (Not Supported) -------------------------------------
    # Elasticsearch user management requires X-Pack security to be enabled
    # and is beyond the scope of this development adapter.
    # The base class provides empty implementations that we inherit.

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate an Elasticsearch connection URL.

        Format: http://host:port or http://username:password@host:port
        """
        if username and password:
            return f"http://{username}:{password}@{host}:{port}"
        return f"http://{host}:{port}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for Elasticsearch."""
        return "elasticsearch"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for Elasticsearch.

        Elasticsearch stores data in /usr/share/elasticsearch/data.
        """
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/usr/share/elasticsearch/data"
        return volumes

    def get_startup_probe_delay(self) -> int:
        """
        Elasticsearch requires a longer startup delay due to JVM initialization.

        Return 30 seconds before first health check.
        """
        return 30
