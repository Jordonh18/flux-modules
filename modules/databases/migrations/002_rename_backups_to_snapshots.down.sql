-- Revert snapshots back to backups

-- Drop new index
DROP INDEX IF EXISTS idx_databases_snapshots_database_id;

-- Rename columns back
ALTER TABLE databases_snapshots RENAME COLUMN snapshot_path TO backup_path;
ALTER TABLE databases_snapshots RENAME COLUMN snapshot_size TO backup_size;

-- Rename table back
ALTER TABLE databases_snapshots RENAME TO databases_backups;

-- Recreate old index
CREATE INDEX IF NOT EXISTS idx_databases_backups_database_id ON databases_backups(database_id);
