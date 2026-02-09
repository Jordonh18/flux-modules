"""
Base Database Adapter — Abstract interface for all database engine adapters.

Every adapter must subclass BaseAdapter and implement all abstract methods.
The adapter pattern isolates database-specific logic (container config, health checks,
metrics, backup/restore, user/database management) from the orchestration layer.

Data classes define shared structures for container configuration, health status,
metrics data, and backup information.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# =============================================================================
# Data Classes
# =============================================================================

class DatabaseCategory(str, Enum):
    """Database engine categories"""
    RELATIONAL = "relational"
    DOCUMENT = "document"
    KEY_VALUE = "key_value"
    WIDE_COLUMN = "wide_column"
    TIME_SERIES = "time_series"
    SEARCH = "search"
    GRAPH = "graph"
    ANALYTICAL = "analytical"
    EMBEDDED = "embedded"


@dataclass
class ContainerConfig:
    """Configuration for creating a database container via Podman."""
    image: str
    default_port: int
    env_vars: dict[str, str] = field(default_factory=dict)
    env_file_vars: dict[str, str] = field(default_factory=dict)  # Vars that use _FILE suffix
    command: list[str] = field(default_factory=list)  # Optional command override
    volumes: dict[str, str] = field(default_factory=dict)  # host_path: container_path
    capabilities: list[str] = field(default_factory=list)  # Extra caps needed
    extra_ports: dict[int, int] = field(default_factory=dict)  # Additional host:container port mappings
    min_memory_mb: int = 512
    min_cpu: float = 0.5
    tmpfs_mounts: dict[str, str] = field(default_factory=dict)  # container_path: options
    health_check_interval: int = 30  # seconds
    startup_timeout: int = 60  # seconds


@dataclass
class HealthStatus:
    """Result of a health check."""
    healthy: bool
    status: str  # "healthy", "unhealthy", "degraded", "unknown"
    response_time_ms: int = 0
    message: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class MetricsData:
    """Database performance metrics."""
    connections: int = 0
    active_queries: int = 0
    queries_per_sec: Optional[float] = None
    cache_hit_ratio: Optional[float] = None
    uptime_seconds: Optional[int] = None
    total_transactions: Optional[int] = None
    slow_queries: Optional[int] = None
    storage_used_mb: Optional[float] = None
    storage_total_mb: Optional[float] = None
    custom: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "connections": self.connections,
            "active_queries": self.active_queries,
            "queries_per_sec": self.queries_per_sec,
            "cache_hit_ratio": self.cache_hit_ratio,
            "uptime_seconds": self.uptime_seconds,
            "total_transactions": self.total_transactions,
            "slow_queries": self.slow_queries,
            "storage_used_mb": self.storage_used_mb,
            "storage_total_mb": self.storage_total_mb,
        }
        result.update(self.custom)
        return result


@dataclass
class BackupInfo:
    """Information about a backup operation."""
    success: bool
    backup_path: str = ""
    backup_size: int = 0
    message: str = ""
    backup_type: str = "logical"  # logical, physical, snapshot


@dataclass
class DatabaseUser:
    """Database user information."""
    username: str
    has_password: bool = True
    permissions: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)


@dataclass
class DatabaseInfo:
    """Database/schema/keyspace information."""
    name: str
    size_mb: Optional[float] = None
    tables_count: Optional[int] = None
    owner: Optional[str] = None


# =============================================================================
# Abstract Base Adapter
# =============================================================================

class BaseAdapter(ABC):
    """
    Abstract base class for database engine adapters.

    Each database engine (MySQL, PostgreSQL, MongoDB, etc.) must provide a
    concrete subclass that implements every abstract method below.

    Attributes:
        engine_name: Machine-readable engine identifier (e.g. "mysql").
        display_name: Human-readable name (e.g. "MySQL 8.0").
        category: DatabaseCategory enum value.
        default_port: Default listening port inside the container.
        container_image: Default OCI image reference.
    """

    engine_name: str = ""
    display_name: str = ""
    category: DatabaseCategory = DatabaseCategory.RELATIONAL
    default_port: int = 0
    container_image: str = ""
    supports_databases: bool = True  # Whether the engine has named databases
    supports_users: bool = True  # Whether the engine has user management
    supports_backup: bool = True
    supports_metrics: bool = True
    is_embedded: bool = False  # DuckDB, H2 server mode

    # ---- Container Management ------------------------------------------------

    @abstractmethod
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
        """Return the ContainerConfig needed to create this engine's container."""
        ...

    # ---- Health & Monitoring -------------------------------------------------

    @abstractmethod
    def get_health_check_command(self, username: str, password: str) -> list[str]:
        """Return the command (run inside the container) that checks health."""
        ...

    @abstractmethod
    def parse_health_check_output(self, returncode: int, stdout: str, stderr: str) -> HealthStatus:
        """Parse the output of the health check command into a HealthStatus."""
        ...

    @abstractmethod
    def get_metrics_command(self, database_name: str, username: str, password: str) -> list[str]:
        """Return the command that extracts performance metrics."""
        ...

    @abstractmethod
    def parse_metrics_output(self, stdout: str) -> MetricsData:
        """Parse metrics command output into MetricsData."""
        ...

    # ---- Backup & Restore ----------------------------------------------------

    @abstractmethod
    def get_backup_command(
        self, database_name: str, username: str, password: str, backup_path: str
    ) -> list[str]:
        """Return the command to create a backup (run inside container or via podman exec)."""
        ...

    @abstractmethod
    def get_restore_command(
        self, database_name: str, username: str, password: str, restore_path: str
    ) -> list[str]:
        """Return the command to restore from a backup."""
        ...

    def get_backup_file_extension(self) -> str:
        """Return the file extension for backup files (e.g. '.sql', '.archive')."""
        return ".sql"

    # ---- Database Operations -------------------------------------------------

    def get_create_database_command(self, db_name: str, owner: str, username: str, password: str) -> list[str]:
        """Return command to create a new database/schema/keyspace."""
        return []

    def get_drop_database_command(self, db_name: str, username: str, password: str) -> list[str]:
        """Return command to drop a database/schema/keyspace."""
        return []

    def get_list_databases_command(self, username: str, password: str) -> list[str]:
        """Return command to list all databases."""
        return []

    # ---- User Management -----------------------------------------------------

    def get_create_user_command(
        self, new_username: str, new_password: str, admin_username: str, admin_password: str
    ) -> list[str]:
        """Return command to create a database user."""
        return []

    def get_drop_user_command(self, target_username: str, admin_username: str, admin_password: str) -> list[str]:
        """Return command to drop a database user."""
        return []

    def get_list_users_command(self, username: str, password: str) -> list[str]:
        """Return command to list all users."""
        return []

    # ---- Utilities -----------------------------------------------------------

    def get_connection_string(
        self, host: str, port: int, database: str, username: str, password: str
    ) -> str:
        """Generate a connection string for client applications."""
        return ""

    def get_log_parser_type(self) -> str:
        """Return the log format type for structured log parsing."""
        return "generic"

    def get_config_template_dir(self) -> str:
        """Return the subdirectory name under config_templates/ for this engine."""
        return self.engine_name

    def get_volume_mounts(self, volume_paths: dict[str, str]) -> dict[str, str]:
        """Return host_path -> container_path mappings for data persistence."""
        return {}

    def get_startup_probe_delay(self) -> int:
        """Seconds to wait after container start before first health check."""
        return 5
