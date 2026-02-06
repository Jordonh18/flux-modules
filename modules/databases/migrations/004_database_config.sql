-- Databases Module - Add Advanced Configuration Support
-- Migration: 004_database_config.sql
--
-- Adds columns for SKU tiers, resource limits, external access, and TLS configuration.
-- Required for Phase 6: Advanced Configuration Options

-- Add SKU tier column (d1, d2, d4, d8, d16, custom)
ALTER TABLE module_databases ADD COLUMN sku TEXT DEFAULT 'd1';

-- Add resource limit columns
ALTER TABLE module_databases ADD COLUMN memory_limit_mb INTEGER DEFAULT 2048;
ALTER TABLE module_databases ADD COLUMN cpu_limit REAL DEFAULT 1.0;
ALTER TABLE module_databases ADD COLUMN storage_limit_gb INTEGER DEFAULT 20;

-- Add external access flag
ALTER TABLE module_databases ADD COLUMN external_access BOOLEAN DEFAULT FALSE;

-- Add TLS configuration columns
ALTER TABLE module_databases ADD COLUMN tls_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE module_databases ADD COLUMN tls_cert_path TEXT;
ALTER TABLE module_databases ADD COLUMN tls_key_path TEXT;

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_module_databases_sku ON module_databases(sku);
CREATE INDEX IF NOT EXISTS idx_module_databases_external_access ON module_databases(external_access);
CREATE INDEX IF NOT EXISTS idx_module_databases_tls_enabled ON module_databases(tls_enabled);
