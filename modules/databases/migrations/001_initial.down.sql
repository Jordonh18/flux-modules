-- Rollback migration for Databases module
-- Migration: 001_initial.down.sql
--
-- This file undoes the changes made in 001_initial.sql

-- Drop indexes
DROP INDEX IF EXISTS idx_module_databases_container_name;
DROP INDEX IF EXISTS idx_module_databases_type;

-- Drop table
DROP TABLE IF EXISTS module_databases;
