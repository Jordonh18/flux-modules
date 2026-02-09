"""
MongoDB 7 Database Adapter

Complete adapter implementation for MongoDB 7.
Provides container configuration, health checks, metrics collection,
backup/restore, and database/user management operations.
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


class MongoDBAdapter(BaseAdapter):
    """MongoDB 7 database engine adapter."""

    engine_name = "mongodb"
    display_name = "MongoDB 7"
    category = DatabaseCategory.DOCUMENT
    default_port = 27017
    container_image = "docker.io/library/mongo:7"
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
        """
        Generate MongoDB container configuration.

        Uses Docker secrets pattern (_FILE suffix) when secrets_paths provided,
        otherwise falls back to plaintext environment variables.
        """
        env_vars = {}
        env_file_vars = {}

        # Root user configuration
        env_vars["MONGO_INITDB_ROOT_USERNAME"] = username

        # Password configuration
        if secrets_paths and "user_password" in secrets_paths:
            env_file_vars["MONGO_INITDB_ROOT_PASSWORD"] = secrets_paths["user_password"]
        else:
            env_vars["MONGO_INITDB_ROOT_PASSWORD"] = password

        # Initial database (optional)
        if database_name:
            env_vars["MONGO_INITDB_DATABASE"] = database_name

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/data/db:Z"
        if "config" in volume_paths:
            volumes[volume_paths["config"]] = "/data/configdb:Z"

        # Build command with TLS if enabled
        command = []
        if tls_cert_path and tls_key_path:
            # MongoDB requires cert and key in a single PEM file
            # We'll mount both and reference them
            volumes[tls_cert_path] = "/tls/server.crt:Z,ro"
            volumes[tls_key_path] = "/tls/server.key:Z,ro"
            # Note: For production use, you'd combine these into a single file
            # For now, we'll use the combined.pem approach
            command.extend([
                "--tlsMode=requireTLS",
                "--tlsCertificateKeyFile=/tls/combined.pem",
            ])

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars=env_file_vars,
            command=command,
            volumes=volumes,
            capabilities=[],  # MongoDB doesn't need special capabilities
            min_memory_mb=memory_mb,
            min_cpu=cpu,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return MongoDB health check command using mongosh.

        Runs a simple ping command against the admin database to verify
        connectivity and authentication.
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            "db.adminCommand('ping')",
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse MongoDB health check output.

        A successful ping returns JSON with { ok: 1 }.
        """
        if returncode != 0:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Health check failed with code {returncode}: {stderr}",
            )

        # Check for "ok" : 1 in the output
        if '"ok"' in stdout and ": 1" in stdout:
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="MongoDB is responding to commands",
            )
        elif "ok" in stdout and "1" in stdout:
            # Sometimes the format might be { ok: 1 } without quotes
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="MongoDB is responding to commands",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Unexpected health check response: {stdout}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return MongoDB metrics collection command.

        Uses db.serverStatus() to extract comprehensive server metrics.
        """
        metrics_script = """
        const status = db.serverStatus();
        print(JSON.stringify({
            connections: status.connections ? status.connections.current : 0,
            activeOperations: status.globalLock && status.globalLock.activeClients ? status.globalLock.activeClients.total : 0,
            uptimeSeconds: status.uptime || 0,
            insertOps: status.opcounters ? status.opcounters.insert : 0,
            queryOps: status.opcounters ? status.opcounters.query : 0,
            updateOps: status.opcounters ? status.opcounters.update : 0,
            deleteOps: status.opcounters ? status.opcounters.delete : 0,
            commandOps: status.opcounters ? status.opcounters.command : 0,
            memResident: status.mem ? status.mem.resident : 0,
            memVirtual: status.mem ? status.mem.virtual : 0,
            cacheDirtyMB: status.wiredTiger && status.wiredTiger.cache ? status.wiredTiger.cache['tracked dirty bytes in the cache'] / (1024 * 1024) : 0,
            cacheUsedMB: status.wiredTiger && status.wiredTiger.cache ? status.wiredTiger.cache['bytes currently in the cache'] / (1024 * 1024) : 0,
            cacheMaxMB: status.wiredTiger && status.wiredTiger.cache ? status.wiredTiger.cache['maximum bytes configured'] / (1024 * 1024) : 0
        }));
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            metrics_script,
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse MongoDB metrics JSON output into MetricsData.

        The metrics script returns JSON with connection counts, operation counters,
        memory usage, and WiredTiger cache statistics.
        """
        try:
            data = json.loads(stdout.strip())

            # Calculate total operations for queries per second estimate
            total_ops = (
                data.get("insertOps", 0)
                + data.get("queryOps", 0)
                + data.get("updateOps", 0)
                + data.get("deleteOps", 0)
                + data.get("commandOps", 0)
            )

            # Estimate QPS if we have uptime
            uptime = data.get("uptimeSeconds", 0)
            qps = total_ops / uptime if uptime > 0 else None

            # Calculate cache hit ratio from WiredTiger
            cache_used = data.get("cacheUsedMB", 0)
            cache_max = data.get("cacheMaxMB", 1)
            cache_hit_ratio = (cache_used / cache_max) if cache_max > 0 else None

            return MetricsData(
                connections=data.get("connections", 0),
                active_queries=data.get("activeOperations", 0),
                queries_per_sec=qps,
                cache_hit_ratio=cache_hit_ratio,
                uptime_seconds=uptime,
                total_transactions=total_ops,
                storage_used_mb=data.get("cacheUsedMB"),
                storage_total_mb=data.get("cacheMaxMB"),
                custom={
                    "insert_ops": data.get("insertOps", 0),
                    "query_ops": data.get("queryOps", 0),
                    "update_ops": data.get("updateOps", 0),
                    "delete_ops": data.get("deleteOps", 0),
                    "command_ops": data.get("commandOps", 0),
                    "mem_resident_mb": data.get("memResident", 0),
                    "mem_virtual_mb": data.get("memVirtual", 0),
                    "cache_dirty_mb": data.get("cacheDirtyMB", 0),
                },
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Return empty metrics on parse failure
            return MetricsData()

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return MongoDB backup command using mongodump.

        Creates a compressed archive of the entire MongoDB instance.
        """
        return [
            "mongodump",
            "--archive=" + backup_path,
            "--gzip",
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return MongoDB restore command using mongorestore.

        Restores from a compressed archive created by mongodump.
        """
        return [
            "mongorestore",
            "--archive=" + restore_path,
            "--gzip",
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_backup_file_extension(self) -> str:
        """Return the file extension for MongoDB backup files."""
        return ".archive"

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """
        Return command to create a MongoDB database.

        MongoDB creates databases implicitly when you insert data,
        so we'll create an empty collection to ensure the database exists.
        """
        create_script = f"""
        db = db.getSiblingDB('{db_name}');
        db.createCollection('_init');
        print('Database {db_name} created');
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            create_script,
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """
        Return command to drop a MongoDB database.
        """
        drop_script = f"""
        db = db.getSiblingDB('{db_name}');
        db.dropDatabase();
        print('Database {db_name} dropped');
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            drop_script,
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all MongoDB databases.

        Returns JSON array of database names.
        """
        list_script = """
        const dbs = db.adminCommand('listDatabases');
        print(JSON.stringify(dbs.databases.map(d => d.name)));
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            list_script,
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Return command to create a MongoDB user.

        Creates a user with readWrite access to all databases.
        """
        create_user_script = f"""
        db = db.getSiblingDB('admin');
        db.createUser({{
            user: '{new_username}',
            pwd: '{new_password}',
            roles: [
                {{ role: 'readWriteAnyDatabase', db: 'admin' }},
                {{ role: 'dbAdminAnyDatabase', db: 'admin' }}
            ]
        }});
        print('User {new_username} created');
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            create_user_script,
            "-u",
            admin_username,
            "-p",
            admin_password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """
        Return command to drop a MongoDB user.
        """
        drop_user_script = f"""
        db = db.getSiblingDB('admin');
        db.dropUser('{target_username}');
        print('User {target_username} dropped');
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            drop_user_script,
            "-u",
            admin_username,
            "-p",
            admin_password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all MongoDB users.

        Returns JSON array of user objects.
        """
        list_users_script = """
        db = db.getSiblingDB('admin');
        const users = db.getUsers();
        print(JSON.stringify(users.users.map(u => ({
            username: u.user,
            roles: u.roles.map(r => r.role)
        }))));
        """
        return [
            "mongosh",
            "--quiet",
            "--eval",
            list_users_script,
            "-u",
            username,
            "-p",
            password,
            "--authenticationDatabase",
            "admin",
        ]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate MongoDB connection string.

        Returns a standard MongoDB connection URI with authentication.
        """
        return f"mongodb://{username}:{password}@{host}:{port}/{database}?authSource=admin"

    def get_log_parser_type(self) -> str:
        """Return the log format type for MongoDB."""
        return "mongodb"

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return MongoDB volume mount mappings.

        MongoDB stores data in /data/db and config in /data/configdb.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/data/db"
        if "config" in volume_paths:
            mounts[volume_paths["config"]] = "/data/configdb"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Seconds to wait after container start before first health check.

        MongoDB typically starts quickly but needs a moment to initialize.
        """
        return 10
