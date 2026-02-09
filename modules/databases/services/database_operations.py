import logging
from typing import Optional
from module_sdk import text, AsyncSession
from .. import INSTANCES_TABLE
from .adapters import get_adapter
from .container_orchestrator import ContainerOrchestrator

logger = logging.getLogger("uvicorn.error")


class DatabaseOperations:
    """Service for managing database-level and user-level operations within managed database instances."""

    @staticmethod
    async def _get_instance_info(db: AsyncSession, instance_id: int) -> dict:
        """
        Retrieve instance information from the database.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            
        Returns:
            dict: Instance information including container_name, database_type, username, password
            
        Raises:
            ValueError: If instance not found
        """
        result = await db.execute(
            text(f'SELECT container_name, database_type, username, password FROM "{INSTANCES_TABLE}" WHERE id = :instance_id'),
            {"instance_id": instance_id}
        )
        row = result.fetchone()
        
        if not row:
            raise ValueError(f"Instance {instance_id} not found")
        
        return {
            "container_name": row[0],
            "database_type": row[1],
            "username": row[2],
            "password": row[3]
        }

    @staticmethod
    async def create_database(
        db: AsyncSession,
        instance_id: int,
        db_name: str,
        owner: Optional[str] = None
    ) -> dict:
        """
        Create a new database in a managed instance.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            db_name: Name of the database to create
            owner: Optional database owner username
            
        Returns:
            dict: {success: bool, message: str}
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_create_database_command(db_name, owner)
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                logger.info(f"Database '{db_name}' created successfully in instance {instance_id}")
                return {"success": True, "message": f"Database '{db_name}' created successfully"}
            else:
                logger.error(f"Failed to create database '{db_name}' in instance {instance_id}: {output}")
                return {"success": False, "message": f"Failed to create database: {output}"}
                
        except Exception as e:
            logger.error(f"Error creating database '{db_name}' in instance {instance_id}: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    async def drop_database(db: AsyncSession, instance_id: int, db_name: str) -> dict:
        """
        Drop a database from a managed instance.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            db_name: Name of the database to drop
            
        Returns:
            dict: {success: bool, message: str}
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_drop_database_command(db_name)
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                logger.info(f"Database '{db_name}' dropped successfully from instance {instance_id}")
                return {"success": True, "message": f"Database '{db_name}' dropped successfully"}
            else:
                logger.error(f"Failed to drop database '{db_name}' from instance {instance_id}: {output}")
                return {"success": False, "message": f"Failed to drop database: {output}"}
                
        except Exception as e:
            logger.error(f"Error dropping database '{db_name}' from instance {instance_id}: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    async def list_databases(db: AsyncSession, instance_id: int) -> list:
        """
        List all databases in a managed instance.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            
        Returns:
            list: List of database names
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_list_databases_command()
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                databases = adapter.parse_list_output(output)
                logger.info(f"Listed {len(databases)} databases from instance {instance_id}")
                return databases
            else:
                logger.error(f"Failed to list databases from instance {instance_id}: {output}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing databases from instance {instance_id}: {str(e)}")
            return []

    @staticmethod
    async def create_user(
        db: AsyncSession,
        instance_id: int,
        new_username: str,
        new_password: str
    ) -> dict:
        """
        Create a new user in a managed instance.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            new_username: Username for the new user
            new_password: Password for the new user
            
        Returns:
            dict: {success: bool, message: str}
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_create_user_command(new_username, new_password)
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                logger.info(f"User '{new_username}' created successfully in instance {instance_id}")
                return {"success": True, "message": f"User '{new_username}' created successfully"}
            else:
                logger.error(f"Failed to create user '{new_username}' in instance {instance_id}: {output}")
                return {"success": False, "message": f"Failed to create user: {output}"}
                
        except Exception as e:
            logger.error(f"Error creating user '{new_username}' in instance {instance_id}: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    async def drop_user(db: AsyncSession, instance_id: int, target_username: str) -> dict:
        """
        Drop a user from a managed instance.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            target_username: Username to drop
            
        Returns:
            dict: {success: bool, message: str}
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_drop_user_command(target_username)
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                logger.info(f"User '{target_username}' dropped successfully from instance {instance_id}")
                return {"success": True, "message": f"User '{target_username}' dropped successfully"}
            else:
                logger.error(f"Failed to drop user '{target_username}' from instance {instance_id}: {output}")
                return {"success": False, "message": f"Failed to drop user: {output}"}
                
        except Exception as e:
            logger.error(f"Error dropping user '{target_username}' from instance {instance_id}: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    async def list_users(db: AsyncSession, instance_id: int) -> list:
        """
        List all users in a managed instance.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            
        Returns:
            list: List of usernames
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_list_users_command()
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                users = adapter.parse_list_output(output)
                logger.info(f"Listed {len(users)} users from instance {instance_id}")
                return users
            else:
                logger.error(f"Failed to list users from instance {instance_id}: {output}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing users from instance {instance_id}: {str(e)}")
            return []

    @staticmethod
    async def grant_permissions(
        db: AsyncSession,
        instance_id: int,
        username: str,
        database: str,
        permissions: list[str]
    ) -> dict:
        """
        Grant permissions to a user on a database.
        
        Args:
            db: Database session
            instance_id: ID of the database instance
            username: Username to grant permissions to
            database: Database name
            permissions: List of permissions to grant (e.g., ['SELECT', 'INSERT', 'UPDATE'])
            
        Returns:
            dict: {success: bool, message: str}
        """
        try:
            instance_info = await DatabaseOperations._get_instance_info(db, instance_id)
            adapter = get_adapter(
                instance_info["database_type"],
                instance_info["username"],
                instance_info["password"]
            )
            
            command = adapter.get_grant_permissions_command(username, database, permissions)
            exit_code, output = await ContainerOrchestrator.exec_command(
                instance_info["container_name"],
                command
            )
            
            if exit_code == 0:
                logger.info(
                    f"Permissions {permissions} granted to '{username}' on database '{database}' "
                    f"in instance {instance_id}"
                )
                return {
                    "success": True,
                    "message": f"Permissions granted to '{username}' on database '{database}'"
                }
            else:
                logger.error(
                    f"Failed to grant permissions to '{username}' on database '{database}' "
                    f"in instance {instance_id}: {output}"
                )
                return {"success": False, "message": f"Failed to grant permissions: {output}"}
                
        except Exception as e:
            logger.error(
                f"Error granting permissions to '{username}' on database '{database}' "
                f"in instance {instance_id}: {str(e)}"
            )
            return {"success": False, "message": str(e)}
