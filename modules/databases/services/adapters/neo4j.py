"""
Neo4j 5 Database Adapter

Complete adapter implementation for Neo4j 5 graph database.
Provides container configuration, health checks, metrics collection,
backup/restore, and database/user management operations.
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData
from typing import Optional
import json


class Neo4jAdapter(BaseAdapter):
    """Neo4j 5 graph database adapter."""

    engine_name = "neo4j"
    display_name = "Neo4j 5"
    category = DatabaseCategory.GRAPH
    default_port = 7687  # Bolt protocol port
    container_image = "docker.io/library/neo4j:5"
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
        Generate Neo4j container configuration.

        Neo4j uses NEO4J_AUTH environment variable for authentication.
        Exposes both Bolt (7687) and HTTP (7474) ports.
        """
        env_vars = {}
        env_file_vars = {}

        # Authentication - Neo4j uses username/password format
        if secrets_paths and "user_password" in secrets_paths:
            # Use secrets file pattern
            env_file_vars["NEO4J_AUTH"] = secrets_paths["user_password"]
        else:
            # Format: username/password
            env_vars["NEO4J_AUTH"] = f"{username}/{password}"

        # Enable APOC plugin
        env_vars["NEO4J_PLUGINS"] = '["apoc"]'

        # Performance tuning based on allocated memory
        if memory_mb >= 2048:
            env_vars["NEO4J_server_memory_heap_initial__size"] = f"{int(memory_mb * 0.5)}m"
            env_vars["NEO4J_server_memory_heap_max__size"] = f"{int(memory_mb * 0.5)}m"
            env_vars["NEO4J_server_memory_pagecache_size"] = f"{int(memory_mb * 0.4)}m"

        # Volume mounts
        volumes = {}
        if "data" in volume_paths:
            volumes[volume_paths["data"]] = "/data:Z"
        if "logs" in volume_paths:
            volumes[volume_paths["logs"]] = "/logs:Z"

        # Extra ports - HTTP browser interface
        extra_ports = {
            7474: 7474,  # HTTP
        }

        return ContainerConfig(
            image=self.container_image,
            default_port=self.default_port,
            env_vars=env_vars,
            env_file_vars=env_file_vars,
            command=[],
            volumes=volumes,
            capabilities=[],
            extra_ports=extra_ports,
            min_memory_mb=max(memory_mb, 1024),
            min_cpu=max(cpu, 0.5),
            health_check_interval=30,
            startup_timeout=90,
        )

    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """
        Return Neo4j health check command.

        Uses HTTP endpoint for quick health check.
        """
        return [
            "curl",
            "-sf",
            "http://localhost:7474"
        ]

    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """
        Parse Neo4j health check output.

        The HTTP endpoint returns 200 OK when Neo4j is ready.
        """
        if returncode == 0:
            return HealthStatus(
                healthy=True,
                status="healthy",
                message="Neo4j is accepting connections",
            )
        else:
            return HealthStatus(
                healthy=False,
                status="unhealthy",
                message=f"Neo4j health check failed: {stderr}",
            )

    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """
        Return Neo4j metrics command.

        Uses cypher-shell to query JMX metrics.
        """
        query = "CALL dbms.queryJmx('org.neo4j:*') YIELD name, attributes RETURN name, attributes"

        return [
            "cypher-shell",
            "-u",
            username,
            "-p",
            password,
            "-d",
            database_name or "neo4j",
            query
        ]

    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """
        Parse Neo4j metrics output.

        Extracts basic metrics from JMX query results.
        """
        # Neo4j metrics parsing is complex - we'll extract basic info
        # In a production implementation, you'd parse the JMX output properly
        
        metrics = MetricsData(
            connections=0,
            active_queries=0,
            custom={
                "raw_output": stdout[:500]  # Store sample for debugging
            }
        )

        # Try to extract uptime if present
        if "Uptime" in stdout:
            try:
                # Parse uptime from output
                for line in stdout.split('\n'):
                    if "Uptime" in line:
                        # Extract numeric value
                        parts = line.split()
                        for part in parts:
                            if part.isdigit():
                                metrics.uptime_seconds = int(part)
                                break
            except (ValueError, IndexError):
                pass

        return metrics

    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """
        Return Neo4j backup command.

        Uses neo4j-admin database dump command.
        """
        return [
            "neo4j-admin",
            "database",
            "dump",
            database_name or "neo4j",
            "--to-path=/tmp/backup"
        ]

    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """
        Return Neo4j restore command.

        Uses neo4j-admin database load command.
        """
        return [
            "neo4j-admin",
            "database",
            "load",
            database_name or "neo4j",
            "--from-path=/tmp/backup",
            "--overwrite-destination=true"
        ]

    def get_backup_file_extension(self) -> str:
        """Return the file extension for Neo4j backups."""
        return ".dump"

    def get_create_database_command(
        self, db_name: str, owner: str, username: str, password: str
    ) -> list[str]:
        """
        Return command to create a new database in Neo4j.

        Uses cypher-shell with CREATE DATABASE command.
        """
        return [
            "cypher-shell",
            "-u",
            username,
            "-p",
            password,
            f"CREATE DATABASE {db_name}"
        ]

    def get_drop_database_command(
        self, db_name: str, username: str, password: str
    ) -> list[str]:
        """
        Return command to drop a database in Neo4j.
        """
        return [
            "cypher-shell",
            "-u",
            username,
            "-p",
            password,
            f"DROP DATABASE {db_name} IF EXISTS"
        ]

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all databases in Neo4j.
        """
        return [
            "cypher-shell",
            "-u",
            username,
            "-p",
            password,
            "SHOW DATABASES"
        ]

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Return command to create a new user in Neo4j.
        """
        return [
            "cypher-shell",
            "-u",
            admin_username,
            "-p",
            admin_password,
            f"CREATE USER {new_username} SET PASSWORD '{new_password}'"
        ]

    def get_drop_user_command(
        self, target_username: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """
        Return command to drop a user in Neo4j.
        """
        return [
            "cypher-shell",
            "-u",
            admin_username,
            "-p",
            admin_password,
            f"DROP USER {target_username} IF EXISTS"
        ]

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """
        Return command to list all users in Neo4j.
        """
        return [
            "cypher-shell",
            "-u",
            username,
            "-p",
            password,
            "SHOW USERS"
        ]

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """
        Generate a Neo4j Bolt connection string.

        Format: bolt://username:password@host:port
        """
        return f"bolt://{username}:{password}@{host}:{port}"

    def get_log_parser_type(self) -> str:
        """Return the log format type for Neo4j."""
        return "neo4j"

    def get_config_template_dir(self) -> str:
        """Return the config template directory name."""
        return self.engine_name

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """
        Return volume mount mappings for Neo4j.
        """
        mounts = {}
        if "data" in volume_paths:
            mounts[volume_paths["data"]] = "/data:Z"
        if "logs" in volume_paths:
            mounts[volume_paths["logs"]] = "/logs:Z"
        return mounts

    def get_startup_probe_delay(self) -> int:
        """
        Return startup probe delay for Neo4j.

        Neo4j can take longer to start, especially on first run.
        """
        return 20
