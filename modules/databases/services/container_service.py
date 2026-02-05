"""
Container Service for Databases Module

Manages container operations using Podman.
This is fully self-contained within the databases module.
"""

import asyncio
import json
import secrets
import socket
import string
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ContainerStatus(str, Enum):
    """Container status states"""
    RUNNING = "running"
    STOPPED = "stopped"
    CREATED = "created"
    EXITED = "exited"
    UNKNOWN = "unknown"


class DatabaseType(str, Enum):
    """Supported database types"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    MONGODB = "mongodb"
    REDIS = "redis"


# Database container images
DATABASE_IMAGES = {
    DatabaseType.POSTGRESQL: "docker.io/library/postgres:16-alpine",
    DatabaseType.MYSQL: "docker.io/library/mysql:8.0",
    DatabaseType.MARIADB: "docker.io/library/mariadb:11",
    DatabaseType.MONGODB: "docker.io/library/mongo:7",
    DatabaseType.REDIS: "docker.io/library/redis:7-alpine",
}

# Database default ports
DATABASE_PORTS = {
    DatabaseType.POSTGRESQL: 5432,
    DatabaseType.MYSQL: 3306,
    DatabaseType.MARIADB: 3306,
    DatabaseType.MONGODB: 27017,
    DatabaseType.REDIS: 6379,
}


@dataclass
class ContainerInfo:
    """Container information"""
    id: str
    name: str
    image: str
    status: ContainerStatus
    ports: dict[str, int]  # internal_port: external_port
    created: str
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "status": self.status.value,
            "ports": self.ports,
            "created": self.created,
        }


@dataclass
class DatabaseCredentials:
    """Database credentials and connection info"""
    database_type: DatabaseType
    container_name: str
    container_id: str
    host: str
    port: int
    database: str
    username: str
    password: str
    
    def to_dict(self) -> dict:
        return {
            "database_type": self.database_type.value,
            "container_name": self.container_name,
            "container_id": self.container_id,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "password": self.password,
            "connection_string": self.connection_string,
        }
    
    @property
    def connection_string(self) -> str:
        """Generate connection string for the database"""
        if self.database_type == DatabaseType.POSTGRESQL:
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.database_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
            return f"mysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.database_type == DatabaseType.MONGODB:
            return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.database_type == DatabaseType.REDIS:
            return f"redis://:{self.password}@{self.host}:{self.port}/0"
        return ""


class ContainerService:
    """Service for managing containers via Podman"""
    
    # Container name prefix for Flux-managed containers
    CONTAINER_PREFIX = "flux-db-"
    
    @staticmethod
    async def check_podman_installed() -> tuple[bool, Optional[str]]:
        """
        Check if Podman is installed and available.
        Returns (is_installed, version_string)
        """
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                version = stdout.decode().strip()
                return True, version
            return False, None
        except FileNotFoundError:
            return False, None
        except Exception as e:
            print(f"Error checking podman: {e}")
            return False, None
    
    @staticmethod
    async def get_podman_info() -> dict:
        """Get detailed Podman system info"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "info", "--format", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                return json.loads(stdout.decode())
            return {}
        except Exception as e:
            print(f"Error getting podman info: {e}")
            return {}
    
    @staticmethod
    async def install_podman() -> tuple[bool, str]:
        """
        Attempt to install Podman using system package manager.
        Returns (success, message)
        
        Note: This requires the flux user to have appropriate sudo permissions.
        """
        # Detect package manager and distribution
        try:
            # Check for apt (Debian/Ubuntu)
            result = await asyncio.create_subprocess_exec(
                "which", "apt",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
            if result.returncode == 0:
                # Install via apt
                process = await asyncio.create_subprocess_exec(
                    "sudo", "apt", "update",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                process = await asyncio.create_subprocess_exec(
                    "sudo", "apt", "install", "-y", "podman",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    return True, "Podman installed successfully via apt"
                return False, f"Failed to install Podman: {stderr.decode()}"
            
            # Check for dnf (Fedora/RHEL)
            result = await asyncio.create_subprocess_exec(
                "which", "dnf",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
            if result.returncode == 0:
                process = await asyncio.create_subprocess_exec(
                    "sudo", "dnf", "install", "-y", "podman",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    return True, "Podman installed successfully via dnf"
                return False, f"Failed to install Podman: {stderr.decode()}"
            
            return False, "No supported package manager found (apt or dnf)"
            
        except Exception as e:
            return False, f"Error installing Podman: {str(e)}"
    
    @staticmethod
    def find_available_port(start_port: int = 10000, end_port: int = 65000) -> int:
        """Find an available port on the host"""
        for port in range(start_port, end_port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        raise RuntimeError("No available ports found")
    
    @staticmethod
    def generate_password(length: int = 24) -> str:
        """Generate a secure random password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_username() -> str:
        """Generate a random non-root username"""
        adjectives = ["swift", "bright", "calm", "bold", "keen", "wise", "fair", "warm"]
        nouns = ["falcon", "cedar", "river", "summit", "aurora", "maple", "horizon", "crystal"]
        return f"{secrets.choice(adjectives)}_{secrets.choice(nouns)}"
    
    @staticmethod
    async def list_flux_containers() -> list[ContainerInfo]:
        """List all Flux-managed containers"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "ps", "-a", "--format", "json",
                "--filter", f"name={ContainerService.CONTAINER_PREFIX}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            
            if result.returncode != 0:
                return []
            
            containers = json.loads(stdout.decode()) if stdout.decode().strip() else []
            
            return [
                ContainerInfo(
                    id=c.get("Id", "")[:12],
                    name=c.get("Names", [""])[0] if isinstance(c.get("Names"), list) else c.get("Names", ""),
                    image=c.get("Image", ""),
                    status=ContainerStatus(c.get("State", "unknown").lower()) if c.get("State", "").lower() in [s.value for s in ContainerStatus] else ContainerStatus.UNKNOWN,
                    ports={},  # Parse from Ports field if needed
                    created=c.get("Created", ""),
                )
                for c in containers
            ]
        except Exception as e:
            print(f"Error listing containers: {e}")
            return []
    
    @staticmethod
    async def create_database(
        db_type: DatabaseType,
        name: Optional[str] = None,
        database_name: str = "app"
    ) -> DatabaseCredentials:
        """
        Create a new database container with auto-generated credentials.
        """
        # Generate container name
        if name:
            container_name = f"{ContainerService.CONTAINER_PREFIX}{name}"
        else:
            suffix = secrets.token_hex(4)
            container_name = f"{ContainerService.CONTAINER_PREFIX}{db_type.value}-{suffix}"
        
        # Generate credentials
        username = ContainerService.generate_username()
        password = ContainerService.generate_password()
        
        # Find available port
        default_port = DATABASE_PORTS[db_type]
        host_port = ContainerService.find_available_port()
        
        # Get image
        image = DATABASE_IMAGES[db_type]
        
        # Build container command based on database type
        env_vars = []
        if db_type == DatabaseType.POSTGRESQL:
            env_vars = [
                "-e", f"POSTGRES_USER={username}",
                "-e", f"POSTGRES_PASSWORD={password}",
                "-e", f"POSTGRES_DB={database_name}",
            ]
        elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
            env_vars = [
                "-e", f"MYSQL_ROOT_PASSWORD={ContainerService.generate_password()}",  # Separate root password
                "-e", f"MYSQL_USER={username}",
                "-e", f"MYSQL_PASSWORD={password}",
                "-e", f"MYSQL_DATABASE={database_name}",
            ]
        elif db_type == DatabaseType.MONGODB:
            env_vars = [
                "-e", f"MONGO_INITDB_ROOT_USERNAME={username}",
                "-e", f"MONGO_INITDB_ROOT_PASSWORD={password}",
                "-e", f"MONGO_INITDB_DATABASE={database_name}",
            ]
        elif db_type == DatabaseType.REDIS:
            # Redis uses password only
            username = ""
            env_vars = [
                "--requirepass", password,
            ]
        
        # Create container
        cmd = [
            "podman", "run", "-d",
            "--name", container_name,
            "-p", f"{host_port}:{default_port}",
            "--restart", "unless-stopped",
        ] + env_vars + [image]
        
        # Handle Redis differently (requirepass is a command arg, not env)
        if db_type == DatabaseType.REDIS:
            cmd = [
                "podman", "run", "-d",
                "--name", container_name,
                "-p", f"{host_port}:{default_port}",
                "--restart", "unless-stopped",
                image,
                "redis-server", "--requirepass", password,
            ]
        
        try:
            # Create container (with reasonable timeout for image pull + start)
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # Wait up to 5 minutes for container creation (includes image pull time)
                stdout, stderr = await asyncio.wait_for(
                    result.communicate(),
                    timeout=300.0  # 5 minutes
                )
            except asyncio.TimeoutError:
                result.kill()
                raise RuntimeError(
                    "Container creation timed out (5 min). "
                    "This usually means the image is being downloaded. "
                    "Try running 'podman pull " + image + "' manually first."
                )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create container: {stderr.decode()}")
            
            container_id = stdout.decode().strip()[:12]
            
            return DatabaseCredentials(
                database_type=db_type,
                container_name=container_name,
                container_id=container_id,
                host="localhost",
                port=host_port,
                database=database_name if db_type != DatabaseType.REDIS else "0",
                username=username,
                password=password,
            )
            
        except Exception as e:
            raise RuntimeError(f"Error creating database: {str(e)}")
    
    @staticmethod
    async def start_container(name_or_id: str) -> bool:
        """Start a stopped container"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "start", name_or_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    async def stop_container(name_or_id: str) -> bool:
        """Stop a running container"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "stop", name_or_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    async def remove_container(name_or_id: str, force: bool = False) -> bool:
        """Remove a container"""
        try:
            cmd = ["podman", "rm"]
            if force:
                cmd.append("-f")
            cmd.append(name_or_id)
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    async def get_container_logs(name_or_id: str, lines: int = 100) -> str:
        """Get container logs"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "logs", "--tail", str(lines), name_or_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            return stdout.decode() + stderr.decode()
        except Exception as e:
            return f"Error getting logs: {str(e)}"


# Module-level instance
container_service = ContainerService()
