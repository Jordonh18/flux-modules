"""
Backup Service for Databases Module

Manages database backup and restore operations across all supported database engines.
Handles backup creation, restoration, listing, deletion, and retention management.

Uses database-specific adapters to execute engine-specific backup commands and
stores backup metadata in the backups table.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from module_sdk import text, AsyncSession

from .. import INSTANCES_TABLE, BACKUPS_TABLE, SNAPSHOTS_TABLE
from .adapters import get_adapter
from .container_orchestrator import ContainerOrchestrator
from .volume_service import VolumeService

logger = logging.getLogger("uvicorn.error")


class BackupService:
    """Static service class for backup management operations."""

    @staticmethod
    async def create_backup(
        db: AsyncSession,
        instance_id: int,
        backup_type: str = "manual",
        notes: Optional[str] = None
    ) -> dict:
        """
        Create a backup of a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance to backup
            backup_type: Type of backup ("manual", "scheduled", "pre-upgrade")
            notes: Optional notes about the backup

        Returns:
            dict with:
                success: bool
                backup_id: int (if successful)
                path: str (backup file path)
                size: int (bytes)
                message: str
        """
        try:
            # Get instance information
            result = await db.execute(
                text(f'SELECT * FROM "{INSTANCES_TABLE}" WHERE id = :id'),
                {"id": instance_id}
            )
            instance = result.mappings().first()

            if not instance:
                return {
                    "success": False,
                    "message": f"Instance {instance_id} not found"
                }

            if instance["status"] not in ["running", "healthy"]:
                return {
                    "success": False,
                    "message": f"Instance must be running to create backup (current status: {instance['status']})"
                }

            # Get adapter for database type
            adapter = get_adapter(instance["database_type"])
            
            # Generate backup file path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            container_name = instance["container_name"]
            backup_filename = f"{container_name}_{timestamp}{adapter.get_backup_file_extension()}"
            
            # Create backups directory
            base_path = VolumeService.get_base_path()
            backups_dir = base_path / "backups" / container_name
            backups_dir.mkdir(parents=True, exist_ok=True)
            
            backup_path = backups_dir / backup_filename
            container_backup_path = f"/tmp/{backup_filename}"

            # Get backup command from adapter
            backup_command = adapter.get_backup_command(
                database_name=instance["database_name"],
                username=instance["username"],
                password=instance["password"],
                backup_path=container_backup_path
            )

            logger.info(f"Creating backup for instance {instance_id} ({container_name})")
            logger.debug(f"Backup command: {' '.join(backup_command)}")

            # Execute backup command inside container
            success, output = await ContainerOrchestrator.exec_command(
                name_or_id=instance["container_id"] or container_name,
                command=backup_command,
                timeout=600.0  # 10 minutes for large databases
            )

            if not success:
                logger.error(f"Backup command failed: {output}")
                return {
                    "success": False,
                    "message": f"Backup command failed: {output[:200]}"
                }

            # Copy backup file from container to host
            copy_success = await ContainerOrchestrator.copy_from_container(
                name_or_id=instance["container_id"] or container_name,
                src_path=container_backup_path,
                dest_path=str(backup_path)
            )

            if not copy_success:
                return {
                    "success": False,
                    "message": "Failed to copy backup file from container"
                }

            # Clean up temporary file in container
            await ContainerOrchestrator.exec_command(
                name_or_id=instance["container_id"] or container_name,
                command=["rm", "-f", container_backup_path],
                timeout=10.0
            )

            # Get backup file size
            backup_size = BackupService.get_backup_size(str(backup_path))

            # Store backup record in database
            insert_result = await db.execute(
                text(f'''
                    INSERT INTO "{BACKUPS_TABLE}" 
                    (database_id, backup_type, backup_path, backup_size, status, notes)
                    VALUES (:database_id, :backup_type, :backup_path, :backup_size, :status, :notes)
                '''),
                {
                    "database_id": instance_id,
                    "backup_type": backup_type,
                    "backup_path": str(backup_path),
                    "backup_size": backup_size,
                    "status": "completed",
                    "notes": notes
                }
            )
            await db.commit()

            backup_id = insert_result.lastrowid

            logger.info(f"Backup created successfully: {backup_path} ({backup_size} bytes)")

            return {
                "success": True,
                "backup_id": backup_id,
                "path": str(backup_path),
                "size": backup_size,
                "message": f"Backup created successfully ({BackupService._format_size(backup_size)})"
            }

        except Exception as e:
            logger.error(f"Failed to create backup for instance {instance_id}: {e}")
            await db.rollback()
            return {
                "success": False,
                "message": f"Backup creation failed: {str(e)}"
            }

    @staticmethod
    async def restore_backup(
        db: AsyncSession,
        instance_id: int,
        backup_id: int
    ) -> dict:
        """
        Restore a database from a backup.

        Args:
            db: Database session
            instance_id: ID of the database instance
            backup_id: ID of the backup to restore

        Returns:
            dict with success status and message
        """
        try:
            # Get instance information
            result = await db.execute(
                text(f'SELECT * FROM "{INSTANCES_TABLE}" WHERE id = :id'),
                {"id": instance_id}
            )
            instance = result.mappings().first()

            if not instance:
                return {
                    "success": False,
                    "message": f"Instance {instance_id} not found"
                }

            # Get backup information
            backup_result = await db.execute(
                text(f'''
                    SELECT * FROM "{BACKUPS_TABLE}" 
                    WHERE id = :backup_id AND database_id = :instance_id
                '''),
                {"backup_id": backup_id, "instance_id": instance_id}
            )
            backup = backup_result.mappings().first()

            if not backup:
                return {
                    "success": False,
                    "message": f"Backup {backup_id} not found for instance {instance_id}"
                }

            backup_path = backup["backup_path"]
            if not os.path.exists(backup_path):
                return {
                    "success": False,
                    "message": f"Backup file not found: {backup_path}"
                }

            # Get adapter for database type
            adapter = get_adapter(instance["database_type"])

            container_restore_path = f"/tmp/restore_{os.path.basename(backup_path)}"

            logger.info(f"Restoring backup {backup_id} to instance {instance_id}")

            # Copy backup file to container
            copy_success = await ContainerOrchestrator.copy_to_container(
                name_or_id=instance["container_id"] or instance["container_name"],
                src_path=backup_path,
                dest_path=container_restore_path
            )

            if not copy_success:
                return {
                    "success": False,
                    "message": "Failed to copy backup file to container"
                }

            # Get restore command from adapter
            restore_command = adapter.get_restore_command(
                database_name=instance["database_name"],
                username=instance["username"],
                password=instance["password"],
                restore_path=container_restore_path
            )

            logger.debug(f"Restore command: {' '.join(restore_command)}")

            # Execute restore command inside container
            success, output = await ContainerOrchestrator.exec_command(
                name_or_id=instance["container_id"] or instance["container_name"],
                command=restore_command,
                timeout=900.0  # 15 minutes for large restores
            )

            # Clean up temporary file in container
            await ContainerOrchestrator.exec_command(
                name_or_id=instance["container_id"] or instance["container_name"],
                command=["rm", "-f", container_restore_path],
                timeout=10.0
            )

            if not success:
                logger.error(f"Restore command failed: {output}")
                return {
                    "success": False,
                    "message": f"Restore command failed: {output[:200]}"
                }

            logger.info(f"Backup {backup_id} restored successfully to instance {instance_id}")

            return {
                "success": True,
                "message": "Backup restored successfully"
            }

        except Exception as e:
            logger.error(f"Failed to restore backup {backup_id}: {e}")
            return {
                "success": False,
                "message": f"Restore failed: {str(e)}"
            }

    @staticmethod
    async def list_backups(
        db: AsyncSession,
        instance_id: int
    ) -> list:
        """
        List all backups and snapshots for a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            List of backup/snapshot dictionaries
        """
        try:
            # Get backups
            backups_result = await db.execute(
                text(f'''
                    SELECT 
                        id,
                        'backup' as type,
                        backup_type as subtype,
                        backup_path as path,
                        backup_size as size,
                        status,
                        notes,
                        created_at
                    FROM "{BACKUPS_TABLE}"
                    WHERE database_id = :instance_id
                    ORDER BY created_at DESC
                '''),
                {"instance_id": instance_id}
            )
            backups = [dict(row._mapping) for row in backups_result]

            # Get snapshots
            snapshots_result = await db.execute(
                text(f'''
                    SELECT 
                        id,
                        'snapshot' as type,
                        'volume' as subtype,
                        snapshot_path as path,
                        snapshot_size as size,
                        'completed' as status,
                        notes,
                        created_at
                    FROM "{SNAPSHOTS_TABLE}"
                    WHERE database_id = :instance_id
                    ORDER BY created_at DESC
                '''),
                {"instance_id": instance_id}
            )
            snapshots = [dict(row._mapping) for row in snapshots_result]

            # Combine and sort by created_at
            all_backups = backups + snapshots
            all_backups.sort(key=lambda x: x["created_at"], reverse=True)

            return all_backups

        except Exception as e:
            logger.error(f"Failed to list backups for instance {instance_id}: {e}")
            return []

    @staticmethod
    async def delete_backup(
        db: AsyncSession,
        backup_id: int
    ) -> dict:
        """
        Delete a backup.

        Args:
            db: Database session
            backup_id: ID of the backup to delete

        Returns:
            dict with success status and message
        """
        try:
            # Get backup information
            result = await db.execute(
                text(f'SELECT * FROM "{BACKUPS_TABLE}" WHERE id = :backup_id'),
                {"backup_id": backup_id}
            )
            backup = result.mappings().first()

            if not backup:
                return {
                    "success": False,
                    "message": f"Backup {backup_id} not found"
                }

            backup_path = backup["backup_path"]

            # Delete file if it exists
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                    logger.info(f"Deleted backup file: {backup_path}")
                except OSError as e:
                    logger.warning(f"Failed to delete backup file {backup_path}: {e}")

            # Delete database record
            await db.execute(
                text(f'DELETE FROM "{BACKUPS_TABLE}" WHERE id = :backup_id'),
                {"backup_id": backup_id}
            )
            await db.commit()

            return {
                "success": True,
                "message": "Backup deleted successfully"
            }

        except Exception as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            await db.rollback()
            return {
                "success": False,
                "message": f"Delete failed: {str(e)}"
            }

    @staticmethod
    async def prune_old_backups(
        db: AsyncSession,
        instance_id: int,
        retention_days: int = 30
    ) -> dict:
        """
        Delete backups older than retention period for an instance.

        Args:
            db: Database session
            instance_id: ID of the database instance
            retention_days: Number of days to retain backups (default: 30)

        Returns:
            dict with count of deleted backups and message
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)

            # Get old backups
            result = await db.execute(
                text(f'''
                    SELECT id, backup_path 
                    FROM "{BACKUPS_TABLE}"
                    WHERE database_id = :instance_id 
                    AND created_at < :cutoff_date
                    AND backup_type != 'manual'
                '''),
                {"instance_id": instance_id, "cutoff_date": cutoff_date}
            )
            old_backups = result.mappings().all()

            deleted_count = 0
            for backup in old_backups:
                # Delete file if it exists
                if os.path.exists(backup["backup_path"]):
                    try:
                        os.remove(backup["backup_path"])
                        deleted_count += 1
                        logger.debug(f"Deleted old backup: {backup['backup_path']}")
                    except OSError as e:
                        logger.warning(f"Failed to delete backup file {backup['backup_path']}: {e}")

            # Delete database records
            if old_backups:
                await db.execute(
                    text(f'''
                        DELETE FROM "{BACKUPS_TABLE}"
                        WHERE database_id = :instance_id 
                        AND created_at < :cutoff_date
                        AND backup_type != 'manual'
                    '''),
                    {"instance_id": instance_id, "cutoff_date": cutoff_date}
                )
                await db.commit()

            logger.info(f"Pruned {deleted_count} old backups for instance {instance_id}")

            return {
                "success": True,
                "deleted_count": deleted_count,
                "message": f"Deleted {deleted_count} backups older than {retention_days} days"
            }

        except Exception as e:
            logger.error(f"Failed to prune backups for instance {instance_id}: {e}")
            await db.rollback()
            return {
                "success": False,
                "deleted_count": 0,
                "message": f"Prune failed: {str(e)}"
            }

    @staticmethod
    def get_backup_size(backup_path: str) -> int:
        """
        Get the size of a backup file in bytes.

        Args:
            backup_path: Path to the backup file

        Returns:
            File size in bytes, or 0 if file doesn't exist
        """
        try:
            if os.path.exists(backup_path):
                return os.path.getsize(backup_path)
            return 0
        except OSError as e:
            logger.warning(f"Failed to get size of backup {backup_path}: {e}")
            return 0

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """
        Format file size in human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted string (e.g., "1.5 GB")
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
