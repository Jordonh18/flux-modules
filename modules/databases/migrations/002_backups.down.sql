-- Rollback: 002_backups
-- Description: Remove backups table

DROP INDEX IF EXISTS idx_module_database_backups_database_id;
DROP INDEX IF EXISTS idx_module_database_backups_created_at;

DROP TABLE IF EXISTS module_database_backups;
