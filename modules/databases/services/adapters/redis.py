"""
Redis 7 Database Adapter

Complete adapter implementation for Redis 7 (Alpine).
Redis is an in-memory key-value store with support for persistence.
Provides container configuration, health checks, metrics collection,
and backup/restore via RDB snapshots.

Note: Redis does not support traditional named databases or user management.
It uses numbered databases (0-15) and ACL-based authentication.
"""

import re
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


class RedisAdapter(BaseAdapter):
    """Redis 7 database engine adapter."""

    engine_name = "redis"
    display_name = "Redis 7"
    category = DatabaseCategory.KEY_VALUE
    default_port = 6379
    container_image = "docker.io/library/redis:7-alpine"
    supports_databases = False  # Redis uses numbered DBs, not named databases
    supports_users = False  # Redis ACL is handled differently
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
        Generate Redis container configuration.

        Redis requires password via command-line flag, not environment variables.
        Uses secrets file when available for secure password injection.
        """
        # Redis has NO env vars for password — use command override instead
        command = []
        if secrets_paths and "root_password" in secrets_paths:
            # Load password from secrets file at runtime
            command = [
                "sh",
                "-c",
                "redis-server --requirepass $(cat /secrets/root_password) --appendonly yes --dir /data"
            ]
        else:
            # Direct password in command (less secure, but fallback)
            command = [
                "redis-server",
                "--requirepass",
                password,
                "--appendonly",
                "yes",
                "--dir",
                "/data"
            ]

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/data:Z"

        # Redis config file mount (optional)
        if "config" in volume_paths:
            volumes[volume_paths["config"]] = "/usr/local/etc/redis/redis.conf:Z,ro"
            # Override command to use config file
            if secrets_paths and "root_password" in secrets_paths:
                command = [
                    "sh",
                    "-c",
                    "redis-server /usr/local/etc/redis/redis.conf --requirepass $(cat /secrets/root_password)"
                ]
            else:
                command = [
                    "redis-server",
                    "/usr/local/etc/redis/redis.conf",
                    "--requirepass",
                    password
                ]

        # TLS support (Redis 6+)
        if tls_cert_path and tls_key_path:
            volumes[tls_cert_path] = "/tls/server.crt:Z,ro"
            volumes[tls_key_path] = "/tls/server.key:Z,ro"
            # Append TLS flags to command
            tls_flags = [
                "--tls-port", str(port),
                "--port", "0",  # Disable non-TLS port
                "--tls-cert-file", "/tls/server.crt",
                "--tls-key-file", "/tls/server.key",
            ]
            if secrets_paths and "root_password" in secrets_paths:
                command = [
                    "sh",
                    "-c",
                    f"redis-server --requirepass $(cat /secrets/root_password) --appendonly yes --dir /data {' '.join(tls_flags)}"
                ]
            else:
                command.extend(tls_flags)

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars={},  # Redis doesn't use env vars for core config
            env_file_vars={},
            command=command,
            volumes=volumes,
            capabilities=[],  # No special capabilities needed
            extra_ports={},
            min_memory_mb=256,  # Redis is lightweight
            min_cpu=0.5,
            tmpfs_mounts={},
            health_check_interval=30,
            startup_timeout=30,
        )

    # ---- Health & Monitoring -------------------------------------------------

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return Redis health check command.
        
        Uses redis-cli PING command with authentication.
        """
        return [
            "redis-cli",
            "-a", password,
            "--no-auth-warning",  # Suppress password warning
            "ping"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse Redis PING output.
        
        Expected successful output: "PONG"
        """
        if returncode == 0 and "PONG" in stdout.upper():
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="Redis is responding to PING",
                details={"response": stdout.strip()}
            )
        
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=f"Redis health check failed: {stderr or stdout}",
            details={"returncode": returncode, "stderr": stderr}
        )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return Redis metrics collection command.
        
        Uses INFO command to get all server statistics.
        """
        return [
            "redis-cli",
            "-a", password,
            "--no-auth-warning",
            "INFO"
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse Redis INFO output.
        
        Redis INFO returns key:value pairs in sections.
        Extracts:
        - connected_clients
        - uptime_in_seconds
        - total_commands_processed
        - keyspace_hits / keyspace_misses -> cache_hit_ratio
        - used_memory_human -> storage_used_mb
        """
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
                # Client connections
                if key == "connected_clients":
                    metrics.connections = int(value)
                
                # Uptime
                elif key == "uptime_in_seconds":
                    metrics.uptime_seconds = int(value)
                
                # Total commands processed
                elif key == "total_commands_processed":
                    metrics.total_transactions = int(value)
                
                # Memory usage
                elif key == "used_memory":
                    # Convert bytes to MB
                    metrics.storage_used_mb = int(value) / (1024 * 1024)
                
                # Keyspace hits/misses for cache hit ratio
                elif key == "keyspace_hits":
                    hits = int(value)
                    metrics.custom["keyspace_hits"] = hits
                
                elif key == "keyspace_misses":
                    misses = int(value)
                    metrics.custom["keyspace_misses"] = misses
                
                # Commands per second
                elif key == "instantaneous_ops_per_sec":
                    metrics.queries_per_sec = float(value)
                
                # Evicted keys
                elif key == "evicted_keys":
                    metrics.custom["evicted_keys"] = int(value)
                
                # Expired keys
                elif key == "expired_keys":
                    metrics.custom["expired_keys"] = int(value)
                
                # Replication lag
                elif key == "master_repl_offset":
                    metrics.custom["master_repl_offset"] = int(value)
                
            except (ValueError, AttributeError):
                # Skip invalid values
                continue
        
        # Calculate cache hit ratio if we have both hits and misses
        if "keyspace_hits" in metrics.custom and "keyspace_misses" in metrics.custom:
            hits = metrics.custom["keyspace_hits"]
            misses = metrics.custom["keyspace_misses"]
            total = hits + misses
            if total > 0:
                metrics.cache_hit_ratio = hits / total
        
        return metrics

    # ---- Backup & Restore ----------------------------------------------------

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return Redis backup command.
        
        Uses BGSAVE to trigger background snapshot.
        The caller should then copy /data/dump.rdb to backup_path.
        """
        return [
            "redis-cli",
            "-a", password,
            "--no-auth-warning",
            "BGSAVE"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return Redis restore command.
        
        Restoration requires:
        1. Stop Redis
        2. Copy backup dump.rdb to /data/dump.rdb
        3. Restart Redis
        
        This command assumes the caller has already copied the file.
        Returns SHUTDOWN to stop the server (caller should restart container).
        """
        return [
            "redis-cli",
            "-a", password,
            "--no-auth-warning",
            "SHUTDOWN",
            "SAVE"  # Ensure current state is saved before shutdown
        ]

    def get_backup_file_extension(self) -> str:
        """Redis backup files use .rdb extension."""
        return ".rdb"

    # ---- Database Operations -------------------------------------------------
    # Redis does not support named databases (uses DB0-DB15 internally)

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """Redis does not support named databases."""
        return []

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Redis does not support named databases."""
        return []

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """Redis does not support named databases."""
        return []

    # ---- User Management -----------------------------------------------------
    # Redis uses ACL system (Redis 6+) which is different from traditional users

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Redis does not support traditional user management in this adapter."""
        return []

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Redis does not support traditional user management in this adapter."""
        return []

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """Redis does not support traditional user management in this adapter."""
        return []

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate Redis connection string.
        
        Format: redis://:{password}@{host}:{port}/{db_number}
        Note: Redis uses DB numbers (0-15), not named databases.
        """
        db_number = database if database.isdigit() else "0"
        return f"redis://:{password}@{host}:{port}/{db_number}"

    def get_log_parser_type(self) -> str:
        """Redis logs use a custom format."""
        return "redis"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for Redis.
        
        Redis stores data in /data (dump.rdb, appendonly.aof).
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/data"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """Redis starts very quickly."""
        return 3
