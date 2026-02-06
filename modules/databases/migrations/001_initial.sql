-- Databases Module - Schema
-- Migration: 001_initial.sql
--
-- Creates all tables for the databases module.
-- All table names are prefixed with 'databases_' per module conventions.

-- Primary table for managed database instances
CREATE TABLE IF NOT EXISTS databases_instances (
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

CREATE INDEX IF NOT EXISTS idx_databases_instances_container_name ON databases_instances(container_name);
CREATE INDEX IF NOT EXISTS idx_databases_instances_type ON databases_instances(database_type);
CREATE INDEX IF NOT EXISTS idx_databases_instances_status ON databases_instances(status);

-- Backup records
CREATE TABLE IF NOT EXISTS databases_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    backup_path TEXT NOT NULL,
    backup_size INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (database_id) REFERENCES databases_instances(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_databases_backups_database_id ON databases_backups(database_id);
