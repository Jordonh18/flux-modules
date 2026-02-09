"""
Valkey Database Adapter

Complete adapter implementation for Valkey (Redis OSS fork).
Valkey is a high-performance key-value store forked from Redis.
"""

from typing import Optional

from .base import (
    BaseAdapter,
    DatabaseCategory,
    ContainerConfig,
    HealthStatus,
    MetricsData,
)


class ValkeyAdapter(BaseAdapter):
    """Valkey (Redis OSS fork) adapter."""
    
    engine_name = "valkey"
    display_name = "Valkey"
    description = "Open-source Redis alternative maintained by the Linux Foundation"
    category = DatabaseCategory.KEY_VALUE
    default_port = 6379
    container_image = "docker.io/valkey/valkey:latest"
    supports_databases = False
    supports_users = False
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
        """Generate container configuration for Valkey."""
        command = []
        
        if secrets_paths and "root_password" in secrets_paths:
            # Read password from secret file
            command = [
                "sh", "-c",
                "valkey-server --requirepass $(cat /secrets/root_password)"
            ]
        else:
            # Pass password directly
            command = [
                "valkey-server",
                "--requirepass", password
            ]
        
        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/data:Z"
        
        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars={},
            env_file_vars={},
            command=command,
            volumes=volumes,
            capabilities=[],
            extra_ports={},
            min_memory_mb=256,
            min_cpu=0.5,
            tmpfs_mounts={},
            health_check_interval=30,
            startup_timeout=30,
        )
    
    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """Return health check command for Valkey."""
        return [
            "valkey-cli",
            "-a", password,
            "--no-auth-warning",
            "ping"
        ]
    
    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """Parse Valkey PING output."""
        if returncode == 0 and "PONG" in stdout.upper():
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="Valkey is responding to PING",
                details={"response": stdout.strip()}
            )
        
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=f"Valkey health check failed: {stderr or stdout}",
            details={"returncode": returncode, "stderr": stderr}
        )
    
    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """Return metrics collection command for Valkey."""
        return [
            "valkey-cli",
            "-a", password,
            "--no-auth-warning",
            "INFO"
        ]
    
    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """Parse Valkey INFO output (same format as Redis)."""
        metrics = MetricsData()
        
        # Parse INFO output line by line
        for line in stdout.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if ':' not in line:
                continue
            
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            try:
                if key == "connected_clients":
                    metrics.connections = int(value)
                elif key == "uptime_in_seconds":
                    metrics.uptime_seconds = int(value)
                elif key == "total_commands_processed":
                    metrics.total_transactions = int(value)
                elif key == "used_memory":
                    metrics.storage_used_mb = int(value) / (1024 * 1024)
                elif key == "keyspace_hits":
                    metrics.custom["keyspace_hits"] = int(value)
                elif key == "keyspace_misses":
                    metrics.custom["keyspace_misses"] = int(value)
                elif key == "instantaneous_ops_per_sec":
                    metrics.queries_per_sec = float(value)
                elif key == "evicted_keys":
                    metrics.custom["evicted_keys"] = int(value)
                elif key == "expired_keys":
                    metrics.custom["expired_keys"] = int(value)
            except (ValueError, AttributeError):
                continue
        
        # Calculate cache hit ratio
        if "keyspace_hits" in metrics.custom and "keyspace_misses" in metrics.custom:
            hits = metrics.custom["keyspace_hits"]
            misses = metrics.custom["keyspace_misses"]
            total = hits + misses
            if total > 0:
                metrics.cache_hit_ratio = hits / total
        
        return metrics
    
    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """Return Valkey backup command using BGSAVE."""
        return [
            "valkey-cli",
            "-a", password,
            "--no-auth-warning",
            "BGSAVE"
        ]
    
    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """Return Valkey restore command (requires shutdown)."""
        return [
            "valkey-cli",
            "-a", password,
            "--no-auth-warning",
            "SHUTDOWN",
            "SAVE"
        ]
    
    def get_backup_file_extension(self) -> str:
        """Valkey backups use .rdb extension."""
        return ".rdb"
    
    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate Valkey connection string (Redis-compatible)."""
        db_num = database if database.isdigit() else "0"
        return f"redis://:{password}@{host}:{port}/{db_num}"
    
    def get_startup_probe_delay(self) -> int:
        """Valkey starts very quickly."""
        return 3
