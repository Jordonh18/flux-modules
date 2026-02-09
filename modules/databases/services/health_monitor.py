"""
Health Monitor for Databases Module

Performs health checks on database instances and maintains health history.
Executes database-specific health check commands and tracks availability metrics.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from module_sdk import text, AsyncSession

from .. import INSTANCES_TABLE, HEALTH_TABLE
from .adapters import get_adapter
from .container_orchestrator import ContainerOrchestrator

logger = logging.getLogger("uvicorn.error")


class HealthMonitor:
    """Static service class for health monitoring operations."""

    @staticmethod
    async def check_health(
        db: AsyncSession,
        instance_id: int
    ) -> dict:
        """
        Perform a health check on a database instance.

        Executes the database-specific health check command via the adapter,
        measures response time, and stores the result in health history.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            dict with:
                healthy: bool
                status: str ("healthy", "unhealthy", "degraded", "unknown")
                response_time_ms: int
                message: str
                details: dict (optional)
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
                    "healthy": False,
                    "status": "unknown",
                    "response_time_ms": 0,
                    "message": f"Instance {instance_id} not found"
                }

            # Container must be running to perform health check
            container_id = instance["container_id"] or instance["container_name"]
            
            # Check if container is running
            inspect = await ContainerOrchestrator.get_container_inspect(container_id)
            if not inspect.get("running", False):
                health_result = {
                    "healthy": False,
                    "status": "unhealthy",
                    "response_time_ms": 0,
                    "message": f"Container is not running (status: {inspect.get('status', 'unknown')})"
                }
                await HealthMonitor._store_health_check(db, instance_id, health_result)
                return health_result

            # Get adapter for database type
            adapter = get_adapter(instance["database_type"])

            # Get health check command
            health_command = adapter.get_health_check_command(
                username=instance["username"],
                password=instance["password"]
            )

            # Measure response time
            start_time = time.time()

            # Execute health check command
            success, output = await ContainerOrchestrator.exec_command(
                name_or_id=container_id,
                command=health_command,
                timeout=30.0
            )

            response_time_ms = int((time.time() - start_time) * 1000)

            # Parse health check output using adapter
            returncode = 0 if success else 1
            stderr = "" if success else output
            stdout = output if success else ""

            health_status = adapter.parse_health_check_output(
                returncode=returncode,
                stdout=stdout,
                stderr=stderr
            )

            # Build result dictionary
            health_result = {
                "healthy": health_status.healthy,
                "status": health_status.status,
                "response_time_ms": response_time_ms,
                "message": health_status.message or "Health check completed",
                "details": health_status.details
            }

            # Store health check result
            await HealthMonitor._store_health_check(db, instance_id, health_result)

            # Update instance status based on health
            if health_status.healthy:
                new_status = "healthy"
            elif health_status.status == "degraded":
                new_status = "degraded"
            else:
                new_status = "unhealthy"

            if instance["status"] != new_status:
                await db.execute(
                    text(f'''
                        UPDATE "{INSTANCES_TABLE}"
                        SET status = :status, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    '''),
                    {"status": new_status, "id": instance_id}
                )
                await db.commit()
                logger.info(f"Instance {instance_id} status updated: {instance['status']} -> {new_status}")

            logger.debug(f"Health check for instance {instance_id}: {health_result['status']} ({response_time_ms}ms)")

            return health_result

        except Exception as e:
            logger.error(f"Health check failed for instance {instance_id}: {e}")
            error_result = {
                "healthy": False,
                "status": "unknown",
                "response_time_ms": 0,
                "message": f"Health check error: {str(e)}"
            }
            
            # Try to store error result
            try:
                await HealthMonitor._store_health_check(db, instance_id, error_result)
            except Exception:
                pass

            return error_result

    @staticmethod
    async def _store_health_check(
        db: AsyncSession,
        instance_id: int,
        health_result: dict
    ) -> None:
        """
        Store health check result in the health history table.

        Args:
            db: Database session
            instance_id: ID of the database instance
            health_result: Health check result dictionary
        """
        try:
            # Convert details dict to JSON string if present
            details_json = None
            if "details" in health_result and health_result["details"]:
                import json
                details_json = json.dumps(health_result["details"])

            await db.execute(
                text(f'''
                    INSERT INTO "{HEALTH_TABLE}" (
                        database_id,
                        status,
                        response_time_ms,
                        details
                    ) VALUES (
                        :database_id,
                        :status,
                        :response_time_ms,
                        :details
                    )
                '''),
                {
                    "database_id": instance_id,
                    "status": health_result["status"],
                    "response_time_ms": health_result.get("response_time_ms", 0),
                    "details": details_json
                }
            )
            await db.commit()

        except Exception as e:
            logger.error(f"Failed to store health check for instance {instance_id}: {e}")
            await db.rollback()

    @staticmethod
    async def get_health_history(
        db: AsyncSession,
        instance_id: int,
        limit: int = 50
    ) -> list:
        """
        Get recent health check history for a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance
            limit: Maximum number of records to return (default: 50)

        Returns:
            List of health check dictionaries ordered by check time (newest first)
        """
        try:
            result = await db.execute(
                text(f'''
                    SELECT 
                        id,
                        database_id,
                        status,
                        response_time_ms,
                        details,
                        checked_at
                    FROM "{HEALTH_TABLE}"
                    WHERE database_id = :instance_id
                    ORDER BY checked_at DESC
                    LIMIT :limit
                '''),
                {"instance_id": instance_id, "limit": limit}
            )

            health_history = [dict(row._mapping) for row in result]

            logger.debug(f"Retrieved {len(health_history)} health records for instance {instance_id}")

            return health_history

        except Exception as e:
            logger.error(f"Failed to get health history for instance {instance_id}: {e}")
            return []

    @staticmethod
    async def get_uptime_stats(
        db: AsyncSession,
        instance_id: int,
        hours: int = 24
    ) -> dict:
        """
        Calculate uptime statistics from health check history.

        Args:
            db: Database session
            instance_id: ID of the database instance
            hours: Number of hours to calculate stats for (default: 24)

        Returns:
            dict with uptime statistics:
                uptime_percent: float (0-100)
                total_checks: int
                healthy_checks: int
                unhealthy_checks: int
                avg_response_time_ms: float
                max_response_time_ms: int
                min_response_time_ms: int
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            result = await db.execute(
                text(f'''
                    SELECT 
                        COUNT(*) as total_checks,
                        SUM(CASE WHEN status = 'healthy' THEN 1 ELSE 0 END) as healthy_checks,
                        SUM(CASE WHEN status IN ('unhealthy', 'unknown') THEN 1 ELSE 0 END) as unhealthy_checks,
                        AVG(response_time_ms) as avg_response_time,
                        MAX(response_time_ms) as max_response_time,
                        MIN(response_time_ms) as min_response_time
                    FROM "{HEALTH_TABLE}"
                    WHERE database_id = :instance_id
                    AND checked_at >= :cutoff_time
                '''),
                {"instance_id": instance_id, "cutoff_time": cutoff_time}
            )

            row = result.mappings().first()

            if not row or row["total_checks"] == 0:
                return {
                    "uptime_percent": 0.0,
                    "total_checks": 0,
                    "healthy_checks": 0,
                    "unhealthy_checks": 0,
                    "avg_response_time_ms": 0.0,
                    "max_response_time_ms": 0,
                    "min_response_time_ms": 0,
                    "period_hours": hours
                }

            uptime_percent = (row["healthy_checks"] / row["total_checks"]) * 100 if row["total_checks"] > 0 else 0.0

            stats = {
                "uptime_percent": round(uptime_percent, 2),
                "total_checks": row["total_checks"] or 0,
                "healthy_checks": row["healthy_checks"] or 0,
                "unhealthy_checks": row["unhealthy_checks"] or 0,
                "avg_response_time_ms": round(row["avg_response_time"] or 0.0, 2),
                "max_response_time_ms": row["max_response_time"] or 0,
                "min_response_time_ms": row["min_response_time"] or 0,
                "period_hours": hours
            }

            logger.debug(f"Uptime stats for instance {instance_id} (last {hours}h): {uptime_percent:.2f}%")

            return stats

        except Exception as e:
            logger.error(f"Failed to calculate uptime stats for instance {instance_id}: {e}")
            return {
                "uptime_percent": 0.0,
                "total_checks": 0,
                "healthy_checks": 0,
                "unhealthy_checks": 0,
                "avg_response_time_ms": 0.0,
                "max_response_time_ms": 0,
                "min_response_time_ms": 0,
                "period_hours": hours
            }

    @staticmethod
    async def cleanup_old_health_records(
        db: AsyncSession,
        retention_days: int = 30
    ) -> int:
        """
        Delete health records older than retention period.

        Args:
            db: Database session
            retention_days: Number of days to retain health records (default: 30)

        Returns:
            Number of deleted records
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)

            result = await db.execute(
                text(f'''
                    DELETE FROM "{HEALTH_TABLE}"
                    WHERE checked_at < :cutoff_date
                '''),
                {"cutoff_date": cutoff_date}
            )
            await db.commit()

            deleted_count = result.rowcount
            logger.info(f"Cleaned up {deleted_count} old health records (older than {retention_days} days)")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old health records: {e}")
            await db.rollback()
            return 0

    @staticmethod
    async def get_current_status(
        db: AsyncSession,
        instance_id: int
    ) -> dict:
        """
        Get current health status without performing a new check.

        Returns the most recent health check result from the database.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            dict with latest health status or default unhealthy status
        """
        try:
            result = await db.execute(
                text(f'''
                    SELECT 
                        status,
                        response_time_ms,
                        details,
                        checked_at
                    FROM "{HEALTH_TABLE}"
                    WHERE database_id = :instance_id
                    ORDER BY checked_at DESC
                    LIMIT 1
                '''),
                {"instance_id": instance_id}
            )

            row = result.mappings().first()

            if not row:
                return {
                    "healthy": False,
                    "status": "unknown",
                    "response_time_ms": 0,
                    "message": "No health check data available",
                    "checked_at": None
                }

            return {
                "healthy": row["status"] == "healthy",
                "status": row["status"],
                "response_time_ms": row["response_time_ms"] or 0,
                "message": f"Last checked at {row['checked_at']}",
                "checked_at": row["checked_at"],
                "details": row["details"]
            }

        except Exception as e:
            logger.error(f"Failed to get current status for instance {instance_id}: {e}")
            return {
                "healthy": False,
                "status": "unknown",
                "response_time_ms": 0,
                "message": f"Error retrieving status: {str(e)}",
                "checked_at": None
            }
