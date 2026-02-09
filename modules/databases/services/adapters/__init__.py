"""
Adapter Registry — Central registry mapping engine names to adapter instances.

Usage:
    from .adapters import get_adapter, list_adapters
    adapter = get_adapter("postgresql")
"""

from .base import BaseAdapter, DatabaseCategory, ContainerConfig, HealthStatus, MetricsData, BackupInfo

# Import all adapter classes (only implemented adapters)
from .mysql import MySQLAdapter
from .postgresql import PostgreSQLAdapter
from .mongodb import MongoDBAdapter
from .redis import RedisAdapter
from .mariadb import MariaDBAdapter
from .mssql import MSSQLAdapter
from .oracle import OracleAdapter
from .cockroachdb import CockroachDBAdapter
from .couchdb import CouchDBAdapter
from .arangodb import ArangoDBAdapter
from .keydb import KeyDBAdapter
from .valkey import ValkeyAdapter
from .cassandra import CassandraAdapter
from .scylladb import ScyllaDBAdapter
from .influxdb import InfluxDBAdapter
from .timescaledb import TimescaleDBAdapter
from .questdb import QuestDBAdapter
from .meilisearch import MeilisearchAdapter
from .elasticsearch import ElasticsearchAdapter
from .typesense import TypesenseAdapter
from .neo4j import Neo4jAdapter
from .janusgraph import JanusGraphAdapter
from .clickhouse import ClickHouseAdapter
from .duckdb import DuckDBAdapter
from .h2 import H2Adapter

# =============================================================================
# Adapter Registry
# =============================================================================

_ADAPTERS: dict[str, BaseAdapter] = {
    "mysql": MySQLAdapter(),
    "postgresql": PostgreSQLAdapter(),
    "mongodb": MongoDBAdapter(),
    "redis": RedisAdapter(),
    "mariadb": MariaDBAdapter(),
    "mssql": MSSQLAdapter(),
    "oracle": OracleAdapter(),
    "cockroachdb": CockroachDBAdapter(),
    "couchdb": CouchDBAdapter(),
    "arangodb": ArangoDBAdapter(),
    "keydb": KeyDBAdapter(),
    "valkey": ValkeyAdapter(),
    "cassandra": CassandraAdapter(),
    "scylladb": ScyllaDBAdapter(),
    "influxdb": InfluxDBAdapter(),
    "timescaledb": TimescaleDBAdapter(),
    "questdb": QuestDBAdapter(),
    "meilisearch": MeilisearchAdapter(),
    "clickhouse": ClickHouseAdapter(),
    "duckdb": DuckDBAdapter(),
    "h2": H2Adapter(),
    "elasticsearch": ElasticsearchAdapter(),
    "typesense": TypesenseAdapter(),
    "neo4j": Neo4jAdapter(),
    "janusgraph": JanusGraphAdapter(),
}


def get_adapter(engine_name: str) -> BaseAdapter:
    """Get the adapter instance for a database engine.

    Raises:
        ValueError: If the engine name is not registered.
    """
    adapter = _ADAPTERS.get(engine_name)
    if adapter is None:
        supported = ", ".join(sorted(_ADAPTERS.keys()))
        raise ValueError(f"Unknown database engine '{engine_name}'. Supported: {supported}")
    return adapter


def list_adapters() -> dict[str, BaseAdapter]:
    """Return all registered adapters."""
    return dict(_ADAPTERS)


def list_engines() -> list[dict]:
    """Return summary info for all supported engines."""
    engines = []
    for name, adapter in sorted(_ADAPTERS.items()):
        engines.append({
            "engine": name,
            "display_name": adapter.display_name,
            "category": adapter.category.value,
            "default_port": adapter.default_port,
            "image": adapter.container_image,
            "supports_databases": adapter.supports_databases,
            "supports_users": adapter.supports_users,
            "supports_backup": adapter.supports_backup,
            "is_embedded": adapter.is_embedded,
        })
    return engines


__all__ = [
    "BaseAdapter",
    "DatabaseCategory",
    "ContainerConfig",
    "HealthStatus",
    "MetricsData",
    "BackupInfo",
    "get_adapter",
    "list_adapters",
    "list_engines",
]
