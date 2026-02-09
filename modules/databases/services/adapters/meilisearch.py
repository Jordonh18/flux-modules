"""
Meilisearch Database Adapter

Complete adapter implementation for Meilisearch (lightweight search engine).
Provides container configuration, health checks, metrics collection,
backup/restore, and index management via REST API.
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


class MeilisearchAdapter(BaseAdapter):
    """Meilisearch search engine adapter."""

    engine_name = "meilisearch"
    display_name = "Meilisearch"
    description = "Lightning-fast, typo-tolerant search engine for great search experiences"
    category = DatabaseCategory.SEARCH
    default_port = 7700
    container_image = "docker.io/getmeili/meilisearch:latest"
    supports_databases = True  # Indexes are like databases
    supports_users = False  # Meilisearch uses API keys, not users
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
        Generate Meilisearch container configuration.

        Meilisearch uses a master key for authentication and runs in production mode.
        """
        env_vars = {
            "MEILI_ENV": "production",
        }

        # Master key configuration (using password field)
        if secrets_paths and "user_password" in secrets_paths:
            # Read master key from file
            env_vars["MEILI_MASTER_KEY_FILE"] = secrets_paths["user_password"]
        else:
            env_vars["MEILI_MASTER_KEY"] = password

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/meili_data:Z"

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            min_memory_mb=max(memory_mb, 256),
            min_cpu=max(cpu, 0.25),
            health_check_interval=30,
            startup_timeout=30,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Generate curl command to check Meilisearch health endpoint.

        Meilisearch provides a /health endpoint that returns service status.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:7700/health",
        ]

    def parse_health_check_output(
        self, returncode: int, stdout: str, stderr: str
    ) -> HealthStatus:
        """
        Parse Meilisearch health check response.

        Successful response is JSON with status "available".
        """
        if returncode == 0 and stdout:
            try:
                data = json.loads(stdout)
                status = data.get("status", "")
                if status == "available":
                    return HealthStatus(
                        healthy=True,
                        status="healthy",
                        message="Meilisearch is available",
                    )
                else:
                    return HealthStatus(
                        healthy=False,
                        status="degraded",
                        message=f"Meilisearch status: {status}",
                        details=data,
                    )
            except json.JSONDecodeError:
                return HealthStatus(
                    healthy=False,
                    status="unhealthy",
                    message="Invalid health response from Meilisearch",
                    details={"stdout": stdout[:200]},
                )
        else:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Meilisearch health check failed (exit {returncode})",
                details={"stderr": stderr[:200]},
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Generate curl command to collect Meilisearch metrics.

        Meilisearch provides /stats endpoint with database and index statistics.
        """
        return [
            "curl",
            "-sf",
            "-H",
            f"Authorization: Bearer {password}",
            "http://localhost:7700/stats",
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse JSON metrics output from Meilisearch /stats endpoint.

        Returns database size, number of indexes, and document counts.
        """
        try:
            data = json.loads(stdout.strip())
            
            # Extract statistics
            database_size = data.get("databaseSize", 0)
            indexes = data.get("indexes", {})
            
            total_documents = 0
            index_count = len(indexes)
            
            for index_stats in indexes.values():
                total_documents += index_stats.get("numberOfDocuments", 0)
            
            return MetricsData(
                connections=0,  # Meilisearch doesn't expose active connections
                active_queries=0,
                storage_used_mb=round(database_size / 1048576.0, 2) if database_size else None,
                custom={
                    "total_indexes": index_count,
                    "total_documents": total_documents,
                    "is_indexing": data.get("isIndexing", False),
                },
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return MetricsData(
                custom={"parse_error": str(e)}
            )

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Generate curl command to create a Meilisearch dump.

        Meilisearch provides /dumps endpoint to create a complete backup.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -X POST -H 'Authorization: Bearer {password}' http://localhost:7700/dumps | tee {backup_path}",
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Generate command to restore Meilisearch from dump.

        Meilisearch automatically imports dumps on startup if placed in dump directory.
        This is a placeholder - actual restore requires restarting with dump file.
        """
        return [
            "echo",
            "Meilisearch restore requires placing dump file in data directory and restarting",
        ]

    def get_backup_file_extension(self) -> str:
        """Return .dump for Meilisearch dump files."""
        return ".dump"

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """
        Generate curl command to create a new index in Meilisearch.

        Indexes in Meilisearch are like databases in traditional RDBMS.
        """
        return [
            "curl",
            "-sf",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-H",
            f"Authorization: Bearer {password}",
            "-d",
            f'{{"uid": "{db_name}"}}',
            "http://localhost:7700/indexes",
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """Generate curl command to delete an index in Meilisearch."""
        return [
            "curl",
            "-sf",
            "-X",
            "DELETE",
            "-H",
            f"Authorization: Bearer {password}",
            f"http://localhost:7700/indexes/{db_name}",
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """Generate curl command to list all indexes in Meilisearch."""
        return [
            "curl",
            "-sf",
            "-H",
            f"Authorization: Bearer {password}",
            "http://localhost:7700/indexes",
        ]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate Meilisearch connection string (HTTP endpoint)."""
        return f"http://{host}:{port}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for structured log parsing."""
        return "generic"

    def get_config_template_dir(self) -> str:
        """Return the subdirectory name under config_templates/ for this engine."""
        return self.engine_name

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """Return host_path -> container_path mappings for data persistence."""
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/meili_data:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """Seconds to wait after container start before first health check."""
        return 5
