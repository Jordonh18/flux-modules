"""
Metrics Collector for Databases Module

Collects and stores performance metrics for database instances.
Combines container-level stats (CPU, memory) with database-specific metrics
(connections, queries, cache hit ratio, etc.) from engine adapters.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional

from module_sdk import text, AsyncSession

from .. import INSTANCES_TABLE, METRICS_TABLE
from .adapters import get_adapter
from .container_orchestrator import ContainerOrchestrator

logger = logging.getLogger("uvicorn.error")


class MetricsCollector:
    """Static service class for metrics collection and storage."""

    @staticmethod
    async def collect_metrics(
        db: AsyncSession,
        instance_id: int
    ) -> dict:
        """
        Collect current metrics for a database instance.

        Combines container stats (CPU, memory) with database-specific metrics
        (connections, queries, uptime, etc.) and stores them in the metrics table.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            dict with current metrics or error information
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

            if instance["status"] not in ["running", "healthy", "degraded"]:
                return {
                    "success": False,
                    "message": f"Cannot collect metrics for instance in status: {instance['status']}"
                }

            container_id = instance["container_id"] or instance["container_name"]

            # Get container stats (CPU, memory)
            container_stats = await ContainerOrchestrator.get_container_stats(container_id)
            parsed_stats = MetricsCollector.parse_container_stats(container_stats)

            # Get database-specific metrics
            adapter = get_adapter(instance["database_type"])
            
            db_metrics = {
                "connections": 0,
                "active_queries": 0,
                "queries_per_sec": None,
                "cache_hit_ratio": None,
                "uptime_seconds": None,
                "storage_used_mb": None
            }

            if adapter.supports_metrics:
                try:
                    metrics_command = adapter.get_metrics_command(
                        database_name=instance["database_name"],
                        username=instance["username"],
                        password=instance["password"]
                    )

                    if metrics_command:
                        success, output = await ContainerOrchestrator.exec_command(
                            name_or_id=container_id,
                            command=metrics_command,
                            timeout=30.0
                        )

                        if success:
                            metrics_data = adapter.parse_metrics_output(output)
                            db_metrics = {
                                "connections": metrics_data.connections,
                                "active_queries": metrics_data.active_queries,
                                "queries_per_sec": metrics_data.queries_per_sec,
                                "cache_hit_ratio": metrics_data.cache_hit_ratio,
                                "uptime_seconds": metrics_data.uptime_seconds,
                                "storage_used_mb": metrics_data.storage_used_mb
                            }
                        else:
                            logger.warning(f"Failed to collect DB metrics for instance {instance_id}: {output[:200]}")
                
                except Exception as e:
                    logger.warning(f"Error collecting DB metrics for instance {instance_id}: {e}")

            # Combine metrics
            combined_metrics = {
                "cpu_percent": parsed_stats["cpu_percent"],
                "memory_used_mb": parsed_stats["memory_used_mb"],
                "memory_limit_mb": parsed_stats["memory_limit_mb"],
                "memory_percent": parsed_stats["memory_percent"],
                "connections": db_metrics["connections"],
                "active_queries": db_metrics["active_queries"],
                "queries_per_sec": db_metrics["queries_per_sec"],
                "cache_hit_ratio": db_metrics["cache_hit_ratio"],
                "uptime_seconds": db_metrics["uptime_seconds"],
                "storage_used_mb": db_metrics["storage_used_mb"]
            }

            # Store metrics in database
            await MetricsCollector.store_metrics(db, instance_id, combined_metrics)

            logger.debug(f"Collected metrics for instance {instance_id}: CPU={combined_metrics['cpu_percent']:.1f}%, "
                        f"MEM={combined_metrics['memory_percent']:.1f}%, CONN={combined_metrics['connections']}")

            return {
                "success": True,
                "metrics": combined_metrics
            }

        except Exception as e:
            logger.error(f"Failed to collect metrics for instance {instance_id}: {e}")
            return {
                "success": False,
                "message": f"Metrics collection failed: {str(e)}"
            }

    @staticmethod
    async def get_metrics_history(
        db: AsyncSession,
        instance_id: int,
        hours: int = 24
    ) -> list:
        """
        Get metrics history for a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance
            hours: Number of hours of history to retrieve (default: 24)

        Returns:
            List of metrics dictionaries ordered by collection time
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            result = await db.execute(
                text(f'''
                    SELECT 
                        id,
                        database_id,
                        cpu_percent,
                        memory_used_mb,
                        memory_limit_mb,
                        memory_percent,
                        connections,
                        active_queries,
                        queries_per_sec,
                        cache_hit_ratio,
                        uptime_seconds,
                        storage_used_mb,
                        collected_at
                    FROM "{METRICS_TABLE}"
                    WHERE database_id = :instance_id
                    AND collected_at >= :cutoff_time
                    ORDER BY collected_at ASC
                '''),
                {"instance_id": instance_id, "cutoff_time": cutoff_time}
            )

            metrics_history = [dict(row._mapping) for row in result]
            
            logger.debug(f"Retrieved {len(metrics_history)} metric records for instance {instance_id} (last {hours}h)")
            
            return metrics_history

        except Exception as e:
            logger.error(f"Failed to get metrics history for instance {instance_id}: {e}")
            return []

    @staticmethod
    async def store_metrics(
        db: AsyncSession,
        instance_id: int,
        metrics: dict
    ) -> None:
        """
        Store metrics in the database.

        Args:
            db: Database session
            instance_id: ID of the database instance
            metrics: Dictionary containing metric values
        """
        try:
            await db.execute(
                text(f'''
                    INSERT INTO "{METRICS_TABLE}" (
                        database_id,
                        cpu_percent,
                        memory_used_mb,
                        memory_limit_mb,
                        memory_percent,
                        connections,
                        active_queries,
                        queries_per_sec,
                        cache_hit_ratio,
                        uptime_seconds,
                        storage_used_mb
                    ) VALUES (
                        :database_id,
                        :cpu_percent,
                        :memory_used_mb,
                        :memory_limit_mb,
                        :memory_percent,
                        :connections,
                        :active_queries,
                        :queries_per_sec,
                        :cache_hit_ratio,
                        :uptime_seconds,
                        :storage_used_mb
                    )
                '''),
                {
                    "database_id": instance_id,
                    "cpu_percent": metrics.get("cpu_percent", 0.0),
                    "memory_used_mb": metrics.get("memory_used_mb", 0.0),
                    "memory_limit_mb": metrics.get("memory_limit_mb", 0.0),
                    "memory_percent": metrics.get("memory_percent", 0.0),
                    "connections": metrics.get("connections", 0),
                    "active_queries": metrics.get("active_queries", 0),
                    "queries_per_sec": metrics.get("queries_per_sec"),
                    "cache_hit_ratio": metrics.get("cache_hit_ratio"),
                    "uptime_seconds": metrics.get("uptime_seconds"),
                    "storage_used_mb": metrics.get("storage_used_mb")
                }
            )
            await db.commit()

            logger.debug(f"Stored metrics for instance {instance_id}")

        except Exception as e:
            logger.error(f"Failed to store metrics for instance {instance_id}: {e}")
            await db.rollback()
            raise

    @staticmethod
    def parse_container_stats(stats_output: dict) -> dict:
        """
        Parse Podman stats output into standardized metrics.

        Args:
            stats_output: Raw stats dictionary from Podman

        Returns:
            dict with parsed CPU and memory metrics
        """
        metrics = {
            "cpu_percent": 0.0,
            "memory_used_mb": 0.0,
            "memory_limit_mb": 0.0,
            "memory_percent": 0.0
        }

        if not stats_output:
            return metrics

        try:
            # Parse CPU percentage
            cpu_str = stats_output.get("CPUPerc", "0%")
            if cpu_str:
                # Format: "12.34%"
                cpu_match = re.match(r'([\d.]+)%?', str(cpu_str))
                if cpu_match:
                    metrics["cpu_percent"] = float(cpu_match.group(1))

            # Parse memory usage
            mem_usage_str = stats_output.get("MemUsage", "0B / 0B")
            if mem_usage_str and "/" in mem_usage_str:
                # Format: "123.4MiB / 2GiB" or "50MB / 512MB"
                parts = mem_usage_str.split("/")
                if len(parts) == 2:
                    used_str = parts[0].strip()
                    limit_str = parts[1].strip()
                    
                    metrics["memory_used_mb"] = MetricsCollector._parse_memory_size(used_str)
                    metrics["memory_limit_mb"] = MetricsCollector._parse_memory_size(limit_str)

            # Parse memory percentage
            mem_perc_str = stats_output.get("MemPerc", "0%")
            if mem_perc_str:
                # Format: "25.00%"
                mem_match = re.match(r'([\d.]+)%?', str(mem_perc_str))
                if mem_match:
                    metrics["memory_percent"] = float(mem_match.group(1))
            elif metrics["memory_limit_mb"] > 0:
                # Calculate from usage if not provided
                metrics["memory_percent"] = (metrics["memory_used_mb"] / metrics["memory_limit_mb"]) * 100

        except Exception as e:
            logger.warning(f"Error parsing container stats: {e}")

        return metrics

    @staticmethod
    def _parse_memory_size(size_str: str) -> float:
        """
        Parse memory size string to MB.

        Supports formats like: "123.4MiB", "2GiB", "512MB", "1.5GB", "1024KB", "100B"

        Args:
            size_str: Memory size string

        Returns:
            Size in megabytes (MB)
        """
        try:
            size_str = size_str.strip()
            
            # Match number and unit
            match = re.match(r'([\d.]+)\s*([A-Za-z]+)', size_str)
            if not match:
                return 0.0

            value = float(match.group(1))
            unit = match.group(2).upper()

            # Convert to MB
            if unit in ['B', 'BYTES']:
                return value / (1024 * 1024)
            elif unit in ['K', 'KB', 'KIB', 'KILOBYTES']:
                return value / 1024
            elif unit in ['M', 'MB', 'MIB', 'MEGABYTES']:
                return value
            elif unit in ['G', 'GB', 'GIB', 'GIGABYTES']:
                return value * 1024
            elif unit in ['T', 'TB', 'TIB', 'TERABYTES']:
                return value * 1024 * 1024
            else:
                logger.warning(f"Unknown memory unit: {unit}")
                return 0.0

        except Exception as e:
            logger.warning(f"Error parsing memory size '{size_str}': {e}")
            return 0.0

    @staticmethod
    async def get_latest_metrics(
        db: AsyncSession,
        instance_id: int
    ) -> Optional[dict]:
        """
        Get the most recent metrics for a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            dict with latest metrics or None if no metrics found
        """
        try:
            result = await db.execute(
                text(f'''
                    SELECT 
                        id,
                        database_id,
                        cpu_percent,
                        memory_used_mb,
                        memory_limit_mb,
                        memory_percent,
                        connections,
                        active_queries,
                        queries_per_sec,
                        cache_hit_ratio,
                        uptime_seconds,
                        storage_used_mb,
                        collected_at
                    FROM "{METRICS_TABLE}"
                    WHERE database_id = :instance_id
                    ORDER BY collected_at DESC
                    LIMIT 1
                '''),
                {"instance_id": instance_id}
            )

            row = result.mappings().first()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get latest metrics for instance {instance_id}: {e}")
            return None

    @staticmethod
    async def cleanup_old_metrics(
        db: AsyncSession,
        retention_days: int = 7
    ) -> int:
        """
        Delete metrics older than retention period.

        Args:
            db: Database session
            retention_days: Number of days to retain metrics (default: 7)

        Returns:
            Number of deleted records
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)

            result = await db.execute(
                text(f'''
                    DELETE FROM "{METRICS_TABLE}"
                    WHERE collected_at < :cutoff_date
                '''),
                {"cutoff_date": cutoff_date}
            )
            await db.commit()

            deleted_count = result.rowcount
            logger.info(f"Cleaned up {deleted_count} old metric records (older than {retention_days} days)")
            
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")
            await db.rollback()
            return 0
