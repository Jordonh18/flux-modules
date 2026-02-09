"""
Credential Manager for Databases Module

Manages database credentials including generation, storage, retrieval,
rotation, and connection string generation for database instances.
"""

import secrets
import string
import logging
from typing import Optional

from module_sdk import text, AsyncSession

from .. import INSTANCES_TABLE
from .adapters import get_adapter
from .container_orchestrator import ContainerOrchestrator

logger = logging.getLogger("uvicorn.error")


# Word lists for username generation
ADJECTIVES = [
    "quick", "lazy", "happy", "clever", "brave", "calm", "wise", "bold",
    "bright", "cool", "fair", "fine", "free", "kind", "neat", "pure",
    "rare", "real", "rich", "safe", "soft", "tall", "warm", "wild",
    "blue", "dark", "deep", "easy", "even", "fast", "good", "high",
]

NOUNS = [
    "fox", "cat", "dog", "owl", "lion", "bear", "wolf", "tiger",
    "eagle", "hawk", "raven", "crane", "swan", "dove", "crow", "lark",
    "river", "mountain", "ocean", "forest", "meadow", "valley", "peak", "lake",
    "star", "moon", "sun", "cloud", "wind", "rain", "snow", "storm",
]


class CredentialManager:
    """Static service class for credential management operations."""

    @staticmethod
    def generate_password(length: int = 32) -> str:
        """
        Generate a secure random password.

        Args:
            length: Length of the password (default: 32)

        Returns:
            Secure random password string
        """
        # Use a mix of uppercase, lowercase, digits, and symbols
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
        
        # Ensure at least one of each character type
        password = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*()-_=+"),
        ]
        
        # Fill the rest with random characters
        password.extend(secrets.choice(alphabet) for _ in range(length - 4))
        
        # Shuffle to avoid predictable patterns
        import random
        random.shuffle(password)
        
        return ''.join(password)

    @staticmethod
    def generate_username() -> str:
        """
        Generate a random username in adjective_noun format.

        Examples: "quick_fox", "brave_eagle", "wise_mountain"

        Returns:
            Random username string
        """
        adjective = secrets.choice(ADJECTIVES)
        noun = secrets.choice(NOUNS)
        
        # Add random number for uniqueness
        random_num = secrets.randbelow(1000)
        
        return f"{adjective}_{noun}_{random_num}"

    @staticmethod
    async def store_credentials(
        db: AsyncSession,
        instance_id: int,
        username: str,
        password: str
    ) -> None:
        """
        Store credentials for a database instance.

        Note: Currently credentials are stored in the instances table.
        This method updates the username and password fields.

        Args:
            db: Database session
            instance_id: ID of the database instance
            username: Username to store
            password: Password to store
        """
        try:
            await db.execute(
                text(f'''
                    UPDATE "{INSTANCES_TABLE}"
                    SET username = :username,
                        password = :password,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                '''),
                {
                    "username": username,
                    "password": password,
                    "id": instance_id
                }
            )
            await db.commit()

            logger.info(f"Updated credentials for instance {instance_id}")

        except Exception as e:
            logger.error(f"Failed to store credentials for instance {instance_id}: {e}")
            await db.rollback()
            raise

    @staticmethod
    async def get_credentials(
        db: AsyncSession,
        instance_id: int
    ) -> Optional[dict]:
        """
        Get credentials for a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            dict with username and password, or None if not found
        """
        try:
            result = await db.execute(
                text(f'''
                    SELECT username, password
                    FROM "{INSTANCES_TABLE}"
                    WHERE id = :id
                '''),
                {"id": instance_id}
            )

            row = result.mappings().first()

            if not row:
                return None

            return {
                "username": row["username"],
                "password": row["password"]
            }

        except Exception as e:
            logger.error(f"Failed to get credentials for instance {instance_id}: {e}")
            return None

    @staticmethod
    async def get_connection_string(
        db: AsyncSession,
        instance_id: int
    ) -> Optional[str]:
        """
        Generate a connection string for a database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            Connection string, or None if instance not found
        """
        try:
            result = await db.execute(
                text(f'''
                    SELECT 
                        database_type,
                        host,
                        port,
                        database_name,
                        username,
                        password
                    FROM "{INSTANCES_TABLE}"
                    WHERE id = :id
                '''),
                {"id": instance_id}
            )

            row = result.mappings().first()

            if not row:
                logger.warning(f"Instance {instance_id} not found")
                return None

            # Get adapter for database type
            adapter = get_adapter(row["database_type"])

            # Generate connection string using adapter
            connection_string = adapter.get_connection_string(
                host=row["host"],
                port=row["port"],
                database=row["database_name"],
                username=row["username"],
                password=row["password"]
            )

            if not connection_string:
                # Fallback to generic format if adapter doesn't provide one
                connection_string = (
                    f"{row['database_type']}://{row['username']}:{row['password']}"
                    f"@{row['host']}:{row['port']}/{row['database_name']}"
                )

            return connection_string

        except Exception as e:
            logger.error(f"Failed to get connection string for instance {instance_id}: {e}")
            return None

    @staticmethod
    async def rotate_password(
        db: AsyncSession,
        instance_id: int,
        new_password: Optional[str] = None
    ) -> dict:
        """
        Rotate the password for a database instance.

        Generates a new password (or uses provided one), updates it in the database,
        and executes the password change command inside the container.

        Args:
            db: Database session
            instance_id: ID of the database instance
            new_password: Optional new password (generates one if not provided)

        Returns:
            dict with:
                success: bool
                username: str
                password: str (new password)
                message: str
        """
        try:
            # Get instance information
            result = await db.execute(
                text(f'''
                    SELECT 
                        container_id,
                        container_name,
                        database_type,
                        database_name,
                        username,
                        password,
                        status
                    FROM "{INSTANCES_TABLE}"
                    WHERE id = :id
                '''),
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
                    "message": f"Instance must be running to rotate password (status: {instance['status']})"
                }

            # Generate new password if not provided
            if not new_password:
                new_password = CredentialManager.generate_password()

            old_password = instance["password"]
            username = instance["username"]

            # Get adapter
            adapter = get_adapter(instance["database_type"])

            # Get password change command from adapter
            # Most adapters use the create_user_command or similar for password changes
            # We'll need to execute the appropriate SQL/command directly

            container_id = instance["container_id"] or instance["container_name"]

            logger.info(f"Rotating password for instance {instance_id} (user: {username})")

            # For SQL databases, we typically use ALTER USER or equivalent
            # This varies by database type, so we'll handle common cases

            if instance["database_type"] in ["mysql", "mariadb"]:
                # MySQL/MariaDB password change
                password_command = [
                    "mysql",
                    "-u", username,
                    f"-p{old_password}",
                    "-e", f"ALTER USER '{username}'@'%' IDENTIFIED BY '{new_password}';"
                ]
            elif instance["database_type"] == "postgresql":
                # PostgreSQL password change
                password_command = [
                    "psql",
                    "-U", username,
                    "-c", f"ALTER USER {username} WITH PASSWORD '{new_password}';"
                ]
                # Set PGPASSWORD environment variable for authentication
                # Note: podman exec doesn't easily support env vars, so we use psql options
                password_command = [
                    "sh", "-c",
                    f"PGPASSWORD={old_password} psql -U {username} -c \"ALTER USER {username} WITH PASSWORD '{new_password}';\""
                ]
            elif instance["database_type"] == "mongodb":
                # MongoDB password change
                password_command = [
                    "mongosh",
                    "--username", username,
                    "--password", old_password,
                    "--authenticationDatabase", "admin",
                    "--eval",
                    f"db.getSiblingDB('admin').changeUserPassword('{username}', '{new_password}')"
                ]
            elif instance["database_type"] in ["redis", "keydb", "valkey"]:
                # Redis-like databases use CONFIG SET requirepass
                password_command = [
                    "redis-cli",
                    "-a", old_password,
                    "CONFIG", "SET", "requirepass", new_password
                ]
            else:
                # For databases we don't have a specific command for,
                # just update the database record
                logger.warning(f"Password rotation not fully implemented for {instance['database_type']}")
                password_command = None

            # Execute password change command if available
            if password_command:
                success, output = await ContainerOrchestrator.exec_command(
                    name_or_id=container_id,
                    command=password_command,
                    timeout=30.0
                )

                if not success:
                    logger.error(f"Password change command failed: {output}")
                    return {
                        "success": False,
                        "message": f"Failed to change password in database: {output[:200]}"
                    }

            # Update password in database
            await CredentialManager.store_credentials(
                db=db,
                instance_id=instance_id,
                username=username,
                password=new_password
            )

            logger.info(f"Password rotated successfully for instance {instance_id}")

            return {
                "success": True,
                "username": username,
                "password": new_password,
                "message": "Password rotated successfully"
            }

        except Exception as e:
            logger.error(f"Failed to rotate password for instance {instance_id}: {e}")
            await db.rollback()
            return {
                "success": False,
                "message": f"Password rotation failed: {str(e)}"
            }

    @staticmethod
    async def validate_credentials(
        db: AsyncSession,
        instance_id: int
    ) -> dict:
        """
        Validate that stored credentials work for the database instance.

        Args:
            db: Database session
            instance_id: ID of the database instance

        Returns:
            dict with validation result
        """
        try:
            # Get instance information
            result = await db.execute(
                text(f'''
                    SELECT 
                        container_id,
                        container_name,
                        database_type,
                        username,
                        password,
                        status
                    FROM "{INSTANCES_TABLE}"
                    WHERE id = :id
                '''),
                {"id": instance_id}
            )

            instance = result.mappings().first()

            if not instance:
                return {
                    "valid": False,
                    "message": f"Instance {instance_id} not found"
                }

            if instance["status"] not in ["running", "healthy", "degraded"]:
                return {
                    "valid": False,
                    "message": f"Instance is not running (status: {instance['status']})"
                }

            # Get adapter
            adapter = get_adapter(instance["database_type"])

            # Use health check as credential validation
            health_command = adapter.get_health_check_command(
                username=instance["username"],
                password=instance["password"]
            )

            container_id = instance["container_id"] or instance["container_name"]

            success, output = await ContainerOrchestrator.exec_command(
                name_or_id=container_id,
                command=health_command,
                timeout=15.0
            )

            if success:
                return {
                    "valid": True,
                    "message": "Credentials are valid"
                }
            else:
                return {
                    "valid": False,
                    "message": f"Credentials validation failed: {output[:200]}"
                }

        except Exception as e:
            logger.error(f"Failed to validate credentials for instance {instance_id}: {e}")
            return {
                "valid": False,
                "message": f"Validation error: {str(e)}"
            }
