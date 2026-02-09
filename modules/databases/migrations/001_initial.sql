-- Databases Module - Schema
-- Migration: 001_initial.sql
-- Module ID: 620600
-- Table Prefix: 620600_databases
--
-- Creates all tables for the databases module.
-- All table names use the unified module ID prefix: 620600_databases_

-- Primary table for managed database instances
CREATE TABLE IF NOT EXISTS "620600_databases_instances" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id TEXT,
    container_name TEXT NOT NULL UNIQUE,
    database_type TEXT NOT NULL,
    host TEXT NOT NULL DEFAULT 'localhost',
    port INTEGER NOT NULL,
    database_name TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    status TEXT DEFAULT 'creating',
    error_message TEXT,
    volume_path TEXT,
    sku TEXT DEFAULT 'b2',
    memory_limit_mb INTEGER DEFAULT 2048,
    cpu_limit REAL DEFAULT 1.0,
    storage_limit_gb INTEGER DEFAULT 20,
    external_access BOOLEAN DEFAULT FALSE,
    tls_enabled BOOLEAN DEFAULT FALSE,
    tls_cert_path TEXT,
    tls_key_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS "idx_620600_databases_instances_container_name" ON "620600_databases_instances"(container_name);
CREATE INDEX IF NOT EXISTS "idx_620600_databases_instances_type" ON "620600_databases_instances"(database_type);
CREATE INDEX IF NOT EXISTS "idx_620600_databases_instances_status" ON "620600_databases_instances"(status);

-- Snapshot records
CREATE TABLE IF NOT EXISTS "620600_databases_snapshots" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    snapshot_path TEXT NOT NULL,
    snapshot_size INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (database_id) REFERENCES "620600_databases_instances"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "idx_620600_databases_snapshots_database_id" ON "620600_databases_snapshots"(database_id);

-- Backup records
CREATE TABLE IF NOT EXISTS "620600_databases_backups" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    backup_type TEXT NOT NULL DEFAULT 'manual',
    backup_path TEXT NOT NULL,
    backup_size INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (database_id) REFERENCES "620600_databases_instances"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "idx_620600_databases_backups_database_id" ON "620600_databases_backups"(database_id);

-- Health history records
CREATE TABLE IF NOT EXISTS "620600_databases_health_history" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',
    response_time_ms INTEGER,
    details TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (database_id) REFERENCES "620600_databases_instances"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "idx_620600_databases_health_database_id" ON "620600_databases_health_history"(database_id);

-- Metrics history records
CREATE TABLE IF NOT EXISTS "620600_databases_metrics" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    cpu_percent REAL DEFAULT 0.0,
    memory_used_mb REAL DEFAULT 0.0,
    memory_limit_mb REAL DEFAULT 0.0,
    memory_percent REAL DEFAULT 0.0,
    connections INTEGER DEFAULT 0,
    active_queries INTEGER DEFAULT 0,
    queries_per_sec REAL,
    cache_hit_ratio REAL,
    uptime_seconds INTEGER,
    storage_used_mb REAL,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (database_id) REFERENCES "620600_databases_instances"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS "idx_620600_databases_metrics_database_id" ON "620600_databases_metrics"(database_id);
CREATE INDEX IF NOT EXISTS "idx_620600_databases_metrics_collected_at" ON "620600_databases_metrics"(collected_at);
