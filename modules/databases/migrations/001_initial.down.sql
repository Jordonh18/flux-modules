-- Databases Module - Rollback Schema
-- Migration: 001_initial.down.sql
-- Module ID: 620600
--
-- Drops all tables created by this module.

DROP INDEX IF EXISTS "idx_620600_databases_metrics_collected_at";
DROP INDEX IF EXISTS "idx_620600_databases_metrics_database_id";
DROP INDEX IF EXISTS "idx_620600_databases_health_database_id";
DROP INDEX IF EXISTS "idx_620600_databases_backups_database_id";
DROP INDEX IF EXISTS "idx_620600_databases_snapshots_database_id";
DROP INDEX IF EXISTS "idx_620600_databases_instances_container_name";
DROP INDEX IF EXISTS "idx_620600_databases_instances_type";
DROP INDEX IF EXISTS "idx_620600_databases_instances_status";

DROP TABLE IF EXISTS "620600_databases_metrics";
DROP TABLE IF EXISTS "620600_databases_health_history";
DROP TABLE IF EXISTS "620600_databases_backups";
DROP TABLE IF EXISTS "620600_databases_snapshots";
DROP TABLE IF EXISTS "620600_databases_instances";
