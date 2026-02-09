"""
CouchDB 3 Adapter

Complete adapter implementation for Apache CouchDB 3, a document-oriented
NoSQL database that uses HTTP REST API for all operations.

Key characteristics:
- HTTP-based API
- No traditional user management (uses HTTP basic auth)
- Database creation/deletion via HTTP PUT/DELETE
- JSON document storage
- Built-in web UI (Fauxton) on same port
- Replication-based backup strategy
"""

import re
import json
from typing import Optional

from .base import (
    BaseAdapter,
    DatabaseCategory,
    ContainerConfig,
    HealthStatus,
    MetricsData,
)


class CouchDBAdapter(BaseAdapter):
    """Apache CouchDB 3 document database adapter."""

    engine_name = "couchdb"
    display_name = "CouchDB 3"
    description = "Document database with HTTP API and multi-master replication"
    category = DatabaseCategory.DOCUMENT
    default_port = 5984
    container_image = "docker.io/library/couchdb:3"
    supports_databases = True  # CouchDB has named databases
    supports_users = False  # CouchDB uses HTTP auth, not SQL-style users
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
        Generate CouchDB container configuration.

        CouchDB uses COUCHDB_USER and COUCHDB_PASSWORD environment variables.
        Data persists in /opt/couchdb/data.
        """
        env_vars = {}
        
        if secrets_paths and "root_password" in secrets_paths:
            env_vars = {
                "COUCHDB_USER": username,
                "COUCHDB_PASSWORD_FILE": "/secrets/root_password",
            }
        else:
            env_vars = {
                "COUCHDB_USER": username,
                "COUCHDB_PASSWORD": password,
            }

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/opt/couchdb/data:Z"

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            volumes=volumes,
            min_memory_mb=256,
            min_cpu=cpu,
            startup_timeout=30,
        )

    # ---- Health & Monitoring -------------------------------------------------

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Health check via CouchDB _up endpoint.

        The _up endpoint returns {"status":"ok"} when healthy.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:5984/_up"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse CouchDB _up endpoint response.

        Success: returncode 0 and JSON contains "ok" or {"status":"ok"}
        """
        if returncode == 0:
            try:
                data = json.loads(stdout)
                if data.get("status") == "ok" or stdout.strip() == "ok":
                    return HealthStatus(
                        healthy=True,
                        status="healthy",
                        response_time_ms=0,
                        message="CouchDB is running",
                    )
            except json.JSONDecodeError:
                # If plain text "ok" response
                if "ok" in stdout.lower():
                    return HealthStatus(
                        healthy=True,
                        status="healthy",
                        response_time_ms=0,
                        message="CouchDB is running",
                    )
        
        return HealthStatus(
            healthy=False,
            status="unhealthy",
            message=f"Health check failed: {stderr or stdout}",
        )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Collect metrics from CouchDB _stats endpoint.

        Returns JSON with various performance statistics.
        """
        return [
            "curl",
            "-sf",
            "-u",
            f"{username}:{password}",
            "http://localhost:5984/_stats"
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse CouchDB _stats JSON response.

        Example structure:
        {
          "couchdb": {
            "httpd": {
              "requests": {"current": 123}
            },
            "open_databases": {"current": 5},
            "open_os_files": {"current": 10}
          }
        }
        """
        try:
            data = json.loads(stdout)
            couchdb_stats = data.get("couchdb", {})
            
            # Extract metrics
            httpd_requests = couchdb_stats.get("httpd", {}).get("requests", {}).get("current", 0)
            open_dbs = couchdb_stats.get("open_databases", {}).get("current", 0)
            open_files = couchdb_stats.get("open_os_files", {}).get("current", 0)
            
            # Auth cache hits (for cache hit ratio)
            auth_cache_hits = couchdb_stats.get("auth_cache_hits", {}).get("current", 0)
            auth_cache_misses = couchdb_stats.get("auth_cache_misses", {}).get("current", 0)
            
            cache_hit_ratio = None
            if auth_cache_hits + auth_cache_misses > 0:
                cache_hit_ratio = auth_cache_hits / (auth_cache_hits + auth_cache_misses)
            
            return MetricsData(
                connections=0,  # CouchDB doesn't expose persistent connection count
                active_queries=httpd_requests,
                cache_hit_ratio=cache_hit_ratio,
                custom={
                    "open_databases": open_dbs,
                    "open_files": open_files,
                }
            )
        except (json.JSONDecodeError, KeyError):
            pass
        
        return MetricsData()

    # ---- Backup & Restore ----------------------------------------------------

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Backup CouchDB database via replication.

        Downloads all documents from the database and saves to a file.
        Uses _all_docs endpoint with include_docs=true.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -u {username}:{password} 'http://localhost:5984/{database_name}/_all_docs?include_docs=true' > {backup_path}"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Restore CouchDB database from backup file.

        Uses _bulk_docs endpoint to insert all documents at once.
        """
        # First, we need to transform the backup data and POST to _bulk_docs
        # This is a simplified version that assumes the backup file is properly formatted
        return [
            "sh",
            "-c",
            f"curl -sf -X POST -u {username}:{password} -H 'Content-Type: application/json' -d @{restore_path} 'http://localhost:5984/{database_name}/_bulk_docs'"
        ]

    def get_backup_file_extension(self) -> str:
        """CouchDB backups are JSON files."""
        return ".json"

    # ---- Database Operations -------------------------------------------------

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Create a CouchDB database via HTTP PUT.

        CouchDB creates databases by sending PUT request to /{db_name}
        """
        return [
            "curl",
            "-sf",
            "-X", "PUT",
            "-u", f"{username}:{password}",
            f"http://localhost:5984/{db_name}"
        ]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """
        Delete a CouchDB database via HTTP DELETE.
        """
        return [
            "curl",
            "-sf",
            "-X", "DELETE",
            "-u", f"{username}:{password}",
            f"http://localhost:5984/{db_name}"
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        List all CouchDB databases via _all_dbs endpoint.

        Returns JSON array of database names.
        Excludes system databases (_users, _replicator, _global_changes).
        """
        return [
            "sh",
            "-c",
            f"curl -sf -u {username}:{password} 'http://localhost:5984/_all_dbs' | grep -v '_users\\|_replicator\\|_global_changes'"
        ]

    # ---- User Management -----------------------------------------------------

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        CouchDB user creation via _users database.

        Creates a user document in the _users database.
        """
        user_doc = {
            "_id": f"org.couchdb.user:{new_username}",
            "name": new_username,
            "type": "user",
            "roles": [],
            "password": new_password
        }
        
        user_doc_json = json.dumps(user_doc)
        
        return [
            "sh",
            "-c",
            f"curl -sf -X PUT -u {admin_username}:{admin_password} -H 'Content-Type: application/json' -d '{user_doc_json}' 'http://localhost:5984/_users/org.couchdb.user:{new_username}'"
        ]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """
        Delete a CouchDB user.

        First fetches the user doc to get its _rev, then deletes it.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -X DELETE -u {admin_username}:{admin_password} \"http://localhost:5984/_users/org.couchdb.user:{target_username}?rev=$(curl -sf -u {admin_username}:{admin_password} 'http://localhost:5984/_users/org.couchdb.user:{target_username}' | grep -o '\"_rev\":\"[^\"]*\"' | cut -d'\"' -f4)\""
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        List all CouchDB users from _users database.

        Returns all documents from _users except system docs.
        """
        return [
            "sh",
            "-c",
            f"curl -sf -u {username}:{password} 'http://localhost:5984/_users/_all_docs' | grep -o '\"org.couchdb.user:[^\"]*\"' | cut -d':' -f3"
        ]

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate CouchDB connection string.

        CouchDB uses HTTP, so connection strings are HTTP URLs.
        """
        return f"http://{username}:{password}@{host}:{port}/{database}"

    def get_startup_probe_delay(self) -> int:
        """CouchDB starts quickly."""
        return 10
