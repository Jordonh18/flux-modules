"""
ArangoDB Multi-Model Database Adapter

Complete adapter implementation for ArangoDB (multi-model database).
Supports document, graph, and key-value data models with REST API access.
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


class ArangoDBAdapter(BaseAdapter):
    """ArangoDB multi-model database adapter."""
    
    engine_name = "arangodb"
    display_name = "ArangoDB"
    description = "Multi-model database supporting documents, graphs, and key-value pairs"
    category = DatabaseCategory.DOCUMENT
    default_port = 8529
    container_image = "docker.io/arangodb:latest"
    supports_databases = True
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
        """Generate container configuration for ArangoDB."""
        env_vars = {}
        command = []
        
        if secrets_paths and "root_password" in secrets_paths:
            # Load password from secrets file
            command = [
                "sh", "-c",
                'arangod --server.authentication true --server.password "$(cat /secrets/root_password)"'
            ]
        else:
            # Use environment variable
            env_vars["ARANGO_ROOT_PASSWORD"] = password
        
        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/var/lib/arangodb3:Z"
        if "apps" in volume_paths:
            volumes[volume_paths["apps"]] = "/var/lib/arangodb3-apps:Z"
        
        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars={},
            command=command,
            volumes=volumes,
            capabilities=[],
            extra_ports={},
            min_memory_mb=512,
            min_cpu=0.5,
            tmpfs_mounts={},
            health_check_interval=30,
            startup_timeout=60,
        )
    
    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """Return health check command for ArangoDB."""
        return ["curl", "-sf", "http://localhost:8529/_api/version"]
    
    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """Parse ArangoDB health check output."""
        if returncode == 0 and "version" in stdout.lower():
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="ArangoDB is responding",
                details={"response": stdout.strip()}
            )
        
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=f"ArangoDB health check failed: {stderr or stdout}",
            details={"returncode": returncode, "stderr": stderr}
        )
    
    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """Return metrics collection command for ArangoDB."""
        return [
            "curl", "-sf",
            "-u", f"{username}:{password}",
            "http://localhost:8529/_admin/statistics"
        ]
    
    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """Parse ArangoDB statistics output."""
        metrics = MetricsData()
        
        try:
            stats = json.loads(stdout)
            
            # Extract metrics
            metrics.connections = stats.get("client", {}).get("totalConnections", 0)
            metrics.uptime_seconds = stats.get("server", {}).get("uptime", 0)
            
            # Custom metrics
            metrics.custom["requests_total"] = stats.get("http", {}).get("requestsTotal", 0)
            metrics.custom["requests_async"] = stats.get("http", {}).get("requestsAsync", 0)
            metrics.custom["requests_get"] = stats.get("http", {}).get("requestsGet", 0)
            metrics.custom["requests_post"] = stats.get("http", {}).get("requestsPost", 0)
            
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass
        
        return metrics
    
    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """Return ArangoDB backup command using arangodump."""
        return [
            "arangodump",
            "--server.password", password,
            "--server.database", database_name,
            "--output-directory", backup_path,
        ]
    
    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """Return ArangoDB restore command using arangorestore."""
        return [
            "arangorestore",
            "--server.password", password,
            "--server.database", database_name,
            "--input-directory", restore_path,
        ]
    
    def get_backup_file_extension(self) -> str:
        """ArangoDB backups are directories, use .tar for archive."""
        return ".tar"
    
    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """Return command to create ArangoDB database via REST API."""
        payload = json.dumps({"name": db_name})
        return [
            "curl", "-sf", "-X", "POST",
            "-u", f"{username}:{password}",
            "-H", "Content-Type: application/json",
            "-d", payload,
            "http://localhost:8529/_api/database"
        ]
    
    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Return command to drop ArangoDB database via REST API."""
        return [
            "curl", "-sf", "-X", "DELETE",
            "-u", f"{username}:{password}",
            f"http://localhost:8529/_api/database/{db_name}"
        ]
    
    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """Return command to list ArangoDB databases via REST API."""
        return [
            "curl", "-sf",
            "-u", f"{username}:{password}",
            "http://localhost:8529/_api/database"
        ]
    
    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Return command to create ArangoDB user via REST API."""
        payload = json.dumps({
            "user": new_username,
            "passwd": new_password,
            "active": True,
        })
        return [
            "curl", "-sf", "-X", "POST",
            "-u", f"{admin_username}:{admin_password}",
            "-H", "Content-Type: application/json",
            "-d", payload,
            "http://localhost:8529/_api/user"
        ]
    
    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Return command to drop ArangoDB user via REST API."""
        return [
            "curl", "-sf", "-X", "DELETE",
            "-u", f"{admin_username}:{admin_password}",
            f"http://localhost:8529/_api/user/{target_username}"
        ]
    
    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """Return command to list ArangoDB users via REST API."""
        return [
            "curl", "-sf",
            "-u", f"{username}:{password}",
            "http://localhost:8529/_api/user"
        ]
    
    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate ArangoDB connection string."""
        base_url = f"http://{username}:{password}@{host}:{port}"
        if database:
            return f"{base_url}/_db/{database}"
        return base_url
    
    def get_startup_probe_delay(self) -> int:
        """ArangoDB takes a bit longer to start."""
        return 10
