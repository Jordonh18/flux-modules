"""
Databases Module - Database-as-a-Service Management for Flux

Provides containerized database provisioning, lifecycle management, health monitoring,
backup/restore, metrics collection, and multi-engine support via Podman orchestration.

Module ID: 620600
Table Prefix: 620600_databases
"""

__version__ = "2.0.7"

# =============================================================================
# Unified Module Identifier System
# =============================================================================

MODULE_ID = "620600"
MODULE_NAME = "databases"
TABLE_PREFIX = f"{MODULE_ID}_{MODULE_NAME}"

# =============================================================================
# Table Name Constants — Use these everywhere instead of hardcoded strings
# =============================================================================

INSTANCES_TABLE = f"{TABLE_PREFIX}_instances"
SNAPSHOTS_TABLE = f"{TABLE_PREFIX}_snapshots"
BACKUPS_TABLE = f"{TABLE_PREFIX}_backups"
METRICS_TABLE = f"{TABLE_PREFIX}_metrics"
HEALTH_TABLE = f"{TABLE_PREFIX}_health_history"
CREDENTIALS_TABLE = f"{TABLE_PREFIX}_credentials"
USERS_TABLE = f"{TABLE_PREFIX}_users"
DATABASES_TABLE = f"{TABLE_PREFIX}_databases"

# =============================================================================
# Supported Database Engines
# =============================================================================

SUPPORTED_ENGINES = [
    # Relational SQL
    "mysql", "postgresql", "mariadb", "mssql", "oracle", "cockroachdb",
    # Document
    "mongodb", "couchdb", "arangodb",
    # Key-Value
    "redis", "keydb", "valkey",
    # Wide Column
    "cassandra", "scylladb",
    # Time Series
    "influxdb", "timescaledb", "questdb",
    # Search
    "elasticsearch", "meilisearch", "typesense",
    # Graph
    "neo4j", "janusgraph",
    # Analytical
    "clickhouse", "duckdb",
    # Embedded
    "h2",
]
