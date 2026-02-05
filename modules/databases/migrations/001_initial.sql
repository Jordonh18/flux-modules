-- Databases Module - Initial Schema
-- Migration: 001_initial.sql
--
-- This file is automatically executed when the module is first loaded.
-- Migrations are tracked in the module_migrations table.

-- Table for storing database container information
CREATE TABLE IF NOT EXISTS module_databases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id TEXT NOT NULL,
    container_name TEXT NOT NULL UNIQUE,
    database_type TEXT NOT NULL,
    host TEXT NOT NULL DEFAULT 'localhost',
    port INTEGER NOT NULL,
    database_name TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_module_databases_container_name ON module_databases(container_name);
CREATE INDEX IF NOT EXISTS idx_module_databases_type ON module_databases(database_type);
