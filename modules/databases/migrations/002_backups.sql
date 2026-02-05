-- Migration: 002_backups
-- Description: Add backups table for database backup management

CREATE TABLE IF NOT EXISTS module_database_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_id INTEGER NOT NULL,
    backup_path TEXT NOT NULL,
    backup_size INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (database_id) REFERENCES module_databases(id) ON DELETE CASCADE
);

-- Indexes for quick lookups
CREATE INDEX IF NOT EXISTS idx_module_database_backups_database_id ON module_database_backups(database_id);
CREATE INDEX IF NOT EXISTS idx_module_database_backups_created_at ON module_database_backups(created_at);
