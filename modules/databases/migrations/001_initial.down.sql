-- Databases Module - Rollback Schema
-- Migration: 001_initial.down.sql
--
-- Drops all tables created by this module.

DROP INDEX IF EXISTS idx_databases_snapshots_database_id;
DROP INDEX IF EXISTS idx_databases_instances_container_name;
DROP INDEX IF EXISTS idx_databases_instances_type;
DROP INDEX IF EXISTS idx_databases_instances_status;

DROP TABLE IF EXISTS databases_snapshots;
DROP TABLE IF EXISTS databases_instances;
