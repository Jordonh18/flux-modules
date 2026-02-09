-- Rename backups to snapshots for terminology consistency

-- Drop old index
DROP INDEX IF EXISTS idx_databases_backups_database_id;

-- Rename table
ALTER TABLE databases_backups RENAME TO databases_snapshots;

-- Rename columns
ALTER TABLE databases_snapshots RENAME COLUMN backup_path TO snapshot_path;
ALTER TABLE databases_snapshots RENAME COLUMN backup_size TO snapshot_size;

-- Recreate index with new name
CREATE INDEX IF NOT EXISTS idx_databases_snapshots_database_id ON databases_snapshots(database_id);
