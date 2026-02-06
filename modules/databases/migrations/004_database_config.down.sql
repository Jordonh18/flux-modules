-- Databases Module - Rollback Advanced Configuration Support
-- Migration: 004_database_config.down.sql
--
-- Removes SKU, resource limits, external access, and TLS configuration columns.
-- Uses SQLite-compatible table rebuild approach.

-- Drop indexes
DROP INDEX IF EXISTS idx_module_databases_sku;
DROP INDEX IF EXISTS idx_module_databases_external_access;
DROP INDEX IF EXISTS idx_module_databases_tls_enabled;

-- Create new table without config columns
CREATE TABLE module_databases_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    database_type TEXT NOT NULL,
    container_name TEXT NOT NULL,
    container_id TEXT,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    database_name TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    volume_path TEXT,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(name)
);

-- Copy data from old table (excluding config columns)
INSERT INTO module_databases_new 
    (id, name, database_type, container_name, container_id, host, port, 
     database_name, username, password, status, error_message, volume_path,
     created_by, created_at, updated_at)
SELECT id, name, database_type, container_name, container_id, host, port,
       database_name, username, password, status, error_message, volume_path,
       created_by, created_at, updated_at
FROM module_databases;

-- Drop old table
DROP TABLE module_databases;

-- Rename new table to original name
ALTER TABLE module_databases_new RENAME TO module_databases;

-- Recreate original indexes
CREATE INDEX IF NOT EXISTS idx_module_databases_created_by ON module_databases(created_by);
CREATE INDEX IF NOT EXISTS idx_module_databases_status ON module_databases(status);
CREATE INDEX IF NOT EXISTS idx_module_databases_volume_path ON module_databases(volume_path);
