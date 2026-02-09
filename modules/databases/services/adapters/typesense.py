"""
Typesense Database Adapter

Complete adapter implementation for Typesense search engine.
Provides container configuration, health checks, metrics collection,
backup/restore, and collection management operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class TypesenseAdapter(BaseAdapter):
    """Typesense search engine adapter."""

    engine_name = "typesense"
    display_name = "Typesense"
    category = DatabaseCategory.SEARCH
    default_port = 8108
    container_image = "docker.io/typesense/typesense:latest"
    supports_databases = True  # Collections in Typesense
    supports_users = False  # API key-based auth only
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
        Generate Typesense container configuration.

        Uses API key (password) for authentication.
        Supports secrets-based configuration.
        """
        env_vars = {}
        env_file_vars = {}
        command = []

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/data:Z"

        # Command configuration - use secrets if available, otherwise plaintext
        if secrets_paths and "user_password" in secrets_paths:
            # Use secret file for API key
            command = [
                "sh",
                "-c",
                "typesense-server --data-dir /data --api-key $(cat /secrets/root_password) --enable-cors"
            ]
        else:
            # Plaintext API key in command
            command = [
                "--data-dir",
                "/data",
                "--api-key",
                password,
                "--enable-cors"
            ]

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars=env_file_vars,
            command=command,
            volumes=volumes,
            capabilities=[],
            min_memory_mb=max(memory_mb, 256),
            min_cpu=max(cpu, 0.25),
            health_check_interval=30,
            startup_timeout=30,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return Typesense health check command.

        Uses the /health endpoint which returns JSON with "ok": true.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:8108/health"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse Typesense health check output.

        The /health endpoint returns JSON: {"ok": true}
        """
        if returncode != 0:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Health check failed with code {returncode}: {stderr}",
            )

        try:
            data = json.loads(stdout.strip())
            if data.get("ok") is True:
                return HealthStatus(
                    healthy=True,
                    status="healthy",
                    message="Typesense is responding",
                )
            else:
                return HealthStatus(
                    healthy=False,
                    status="degraded",
                    message="Typesense returned non-ok status",
                )
        except (json.JSONDecodeError, KeyError):
            # Check for plain "ok" text response
            if '"ok"' in stdout and 'true' in stdout.lower():
                return HealthStatus(
                    healthy=True,
                    status="healthy",
                    message="Typesense is responding",
                )
            return HealthStatus(
                healthy=False,
                status="unknown",
                message=f"Could not parse health check response: {stdout}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return Typesense metrics command.

        Uses the /metrics.json endpoint with X-TYPESENSE-API-KEY header.
        """
        return [
            "curl",
            "-sf",
            "-H",
            f"X-TYPESENSE-API-KEY: {password}",
            "http://localhost:8108/metrics.json"
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse Typesense metrics JSON output.

        Extracts system and search metrics from the /metrics.json endpoint.
        """
        try:
            data = json.loads(stdout.strip())

            # Extract relevant metrics
            system_cpu = data.get("system_cpu_active_percentage", 0)
            system_memory = data.get("system_memory_used_bytes", 0)
            system_disk = data.get("system_disk_used_bytes", 0)

            # Convert to MB
            memory_mb = system_memory / (1024 * 1024) if system_memory else None
            disk_mb = system_disk / (1024 * 1024) if system_disk else None

            return MetricsData(
                connections=0,  # Typesense doesn't expose active connections count
                active_queries=0,
                uptime_seconds=int(data.get("typesense_process_uptime_seconds", 0)) or None,
                storage_used_mb=disk_mb,
                custom={
                    "cpu_percentage": system_cpu,
                    "memory_used_mb": memory_mb,
                    "total_requests": data.get("typesense_total_requests", 0),
                    "search_requests": data.get("typesense_search_requests", 0),
                    "import_requests": data.get("typesense_import_requests", 0),
                }
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return Typesense backup command.

        Uses the snapshot API to create a backup.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -H 'X-TYPESENSE-API-KEY: {password}' -X POST 'http://localhost:8108/operations/snapshot?snapshot_path=/data/snapshot' && tar -czf {backup_path} -C /data snapshot"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return Typesense restore command.

        Extracts the snapshot and restarts the service to load it.
        """
        return [
            "sh",
            "-c",
            f"tar -xzf {restore_path} -C /data && chmod -R 755 /data/snapshot"
        ]

    def get_backup_file_extension(self) -> str:
        """Return the file extension for Typesense backups."""
        return ".tar.gz"

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """
        Return command to create a new collection in Typesense.

        Collections in Typesense are similar to databases/tables in other systems.
        Creates a minimal schema collection.
        """
        schema = {
            "name": db_name,
            "fields": [
                {"name": "id", "type": "string"},
                {"name": "data", "type": "string", "optional": True}
            ]
        }
        schema_json = json.dumps(schema).replace('"', '\\"')

        return [
            "sh",
            "-c",
            f"curl -sf -H 'X-TYPESENSE-API-KEY: {password}' -H 'Content-Type: application/json' -X POST 'http://localhost:8108/collections' -d \"{schema_json}\""
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """
        Return command to drop a collection in Typesense.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -H 'X-TYPESENSE-API-KEY: {password}' -X DELETE 'http://localhost:8108/collections/{db_name}'"
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all collections in Typesense.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -H 'X-TYPESENSE-API-KEY: {password}' 'http://localhost:8108/collections'"
        ]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Typesense doesn't support user management - uses API keys only.
        """
        return []

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Typesense doesn't support user management - uses API keys only.
        """
        return []

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Typesense doesn't support user management - uses API keys only.
        """
        return []

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate a Typesense connection string.

        Format: http://host:port
        """
        return f"http://{host}:{port}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for Typesense."""
        return "generic"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return self.engine_name

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for Typesense.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/data:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for Typesense.

        Typesense starts quickly, 5 seconds is sufficient.
        """
        return 5
