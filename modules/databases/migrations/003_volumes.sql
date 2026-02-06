-- Databases Module - Add Volume Path Support
-- Migration: 003_volumes.sql
--
-- Adds persistent volume path tracking to database records.
-- Required for Phase 3: Persistent Storage & Volume Management

-- Add volume_path column to track persistent storage location
ALTER TABLE module_databases ADD COLUMN volume_path TEXT;

-- Create index for volume path lookups (useful for filesystem operations)
CREATE INDEX IF NOT EXISTS idx_module_databases_volume_path ON module_databases(volume_path);
