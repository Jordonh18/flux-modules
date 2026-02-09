"""
InfluxDB 2.7 Database Adapter

Complete adapter implementation for InfluxDB 2.7 (time-series database).
Provides container configuration, health checks, metrics collection,
backup/restore, and bucket/token management operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class InfluxDBAdapter(BaseAdapter):
    """InfluxDB 2.7 time-series database adapter."""

    engine_name = "influxdb"
    display_name = "InfluxDB 2.7"
    category = DatabaseCategory.TIME_SERIES
    default_port = 8086
    container_image = "docker.io/library/influxdb:2.7"
    supports_databases = True  # Buckets
    supports_users = True  # Via tokens/auth
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
        Generate InfluxDB container configuration.

        Uses automated setup mode to initialize with user, org, and bucket.
        """
        env_vars = {
            "DOCKER_INFLUXDB_INIT_MODE": "setup",
            "DOCKER_INFLUXDB_INIT_USERNAME": username,
            "DOCKER_INFLUXDB_INIT_PASSWORD": password,
            "DOCKER_INFLUXDB_INIT_ORG": "flux",
            "DOCKER_INFLUXDB_INIT_BUCKET": database_name or "default",
        }

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/influxdb2:Z"

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            min_memory_mb=512,
            min_cpu=cpu,
            startup_timeout=60,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return health check command using influx ping.

        Alternative: curl the health endpoint.
        """
        # Primary method: use influx CLI ping
        return ["influx", "ping"]
        
        # Alternative method (if influx CLI not available):
        # return ["curl", "-sf", "http://localhost:8086/health"]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse InfluxDB health check output.

        Looks for 'ok' status or successful ping response.
        """
        if returncode == 0:
            stdout_lower = stdout.lower()
            
            # Check for various success indicators
            if "ok" in stdout_lower or "healthy" in stdout_lower or "pass" in stdout_lower:
                return HealthStatus(
                    healthy=True,
                    status="healthy",
                    message="InfluxDB is operational"
                )
            
            # If using curl, check for JSON response
            if "{" in stdout and "status" in stdout_lower:
                try:
                    health_data = json.loads(stdout)
                    if health_data.get("status") == "pass":
                        return HealthStatus(
                            healthy=True,
                            status="healthy",
                            message="InfluxDB is operational",
                            details=health_data
                        )
                except json.JSONDecodeError:
                    pass
        
        # Not healthy
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=stderr or stdout or "Failed to connect to InfluxDB",
            details={"stdout": stdout, "stderr": stderr}
        )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return command to extract metrics from InfluxDB.

        Uses influx query or curl to fetch metrics endpoint.
        """
        # Query internal metrics (requires setup)
        # For simplicity, we'll use the health endpoint which includes metrics
        return ["curl", "-s", "http://localhost:8086/metrics"]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse InfluxDB metrics from Prometheus-format output.

        InfluxDB exposes metrics in Prometheus format at /metrics endpoint.
        """
        metrics = MetricsData()
        
        # Parse Prometheus-style metrics
        lines = stdout.strip().split('\n')
        for line in lines:
            if line.startswith('#') or not line.strip():
                continue
            
            # Look for useful metrics
            if "influxdb_uptime_seconds" in line:
                try:
                    value = float(line.split()[-1])
                    metrics.uptime_seconds = int(value)
                except (ValueError, IndexError):
                    pass
            
            elif "influxdb_queryExecutor_queriesActive" in line:
                try:
                    value = int(float(line.split()[-1]))
                    metrics.active_queries = value
                except (ValueError, IndexError):
                    pass
            
            elif "influxdb_database_numMeasurements" in line:
                try:
                    value = int(float(line.split()[-1]))
                    metrics.custom["num_measurements"] = value
                except (ValueError, IndexError):
                    pass
        
        return metrics

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return command to create an InfluxDB backup.

        Uses influx backup command to create backup in specified path.
        """
        return ["influx", "backup", backup_path]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return command to restore from an InfluxDB backup.

        Uses influx restore command to restore from backup path.
        """
        return ["influx", "restore", restore_path]

    def get_backup_file_extension(self) -> str:
        """InfluxDB backups are directory-based, archived as tarball."""
        return ".tar.gz"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Create a bucket in InfluxDB.

        Uses influx CLI to create a new bucket in the default org.
        """
        return ["influx", "bucket", "create", "--name", db_name, "--org", "flux"]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Delete a bucket from InfluxDB."""
        return ["influx", "bucket", "delete", "--name", db_name, "--org", "flux"]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """List all InfluxDB buckets."""
        return ["influx", "bucket", "list", "--org", "flux"]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Create an InfluxDB user (via auth token).

        InfluxDB 2.x uses token-based authentication rather than traditional users.
        This creates an all-access token for the user.
        """
        return ["influx", "auth", "create", "--org", "flux", "--description", f"Token for {new_username}"]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """
        Drop an InfluxDB auth token.

        Note: This requires knowing the token ID, which is complex.
        In practice, tokens are revoked by ID.
        """
        # This is a placeholder - actual implementation would need token ID lookup
        return ["influx", "auth", "delete", "--id", f"<token_id>"]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """List all InfluxDB auth tokens."""
        return ["influx", "auth", "list", "--org", "flux"]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate InfluxDB connection string.

        InfluxDB uses HTTP API with token-based auth, not a traditional connection string.
        """
        return f"http://{host}:{port}"

    def get_log_parser_type(self) -> str:
        """InfluxDB uses structured JSON logging."""
        return "influxdb"

    def get_startup_probe_delay(self) -> int:
        """InfluxDB starts relatively quickly."""
        return 10
