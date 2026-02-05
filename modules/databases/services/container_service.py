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
    
    # Container name prefix for Flux-managed containers (minimal for filtering)
    CONTAINER_PREFIX = "flux-"
    
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
    def find_available_port(start_port: int = 10000, end_port: int = 65000, exclude_ports: set = None) -> int:
        """Find an available port on the host, excluding already-assigned ports"""
        if exclude_ports is None:
            exclude_ports = set()
        
        for port in range(start_port, end_port):
            # Skip ports already assigned in the database
            if port in exclude_ports:
                continue
                
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
    async def list_flux_containers(container_names: list[str] = None) -> list[ContainerInfo]:
        """List containers by name, or all containers if no names provided"""
        try:
            cmd = ["podman", "ps", "-a", "--format", "json"]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            
            if result.returncode != 0:
                return []
            
            containers = json.loads(stdout.decode()) if stdout.decode().strip() else []
            
            # Filter by names if provided
            if container_names:
                name_set = set(container_names)
                containers = [
                    c for c in containers
                    if (c.get("Names", [""])[0] if isinstance(c.get("Names"), list) else c.get("Names", "")) in name_set
                ]
            
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
        database_name: str = "app",
        container_name: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        host_port: Optional[int] = None
    ) -> DatabaseCredentials:
        """
        Create a new database container with auto-generated or provided credentials.
        """
        # Use provided values or generate new ones
        if not container_name:
            # Generate container name with unique suffix to prevent conflicts
            suffix = secrets.token_hex(4)
            if name:
                # Use custom name + unique suffix (no prefix)
                container_name = f"{name}-{suffix}"
            else:
                # Generate full name using db type + suffix (no prefix)
                container_name = f"{db_type.value}-{suffix}"
        
        # Generate credentials if not provided
        if not username:
            username = ContainerService.generate_username()
        if not password:
            password = ContainerService.generate_password()
        
        # Find available port if not provided
        if not host_port:
            host_port = ContainerService.find_available_port()
        
        # Get default internal port and image
        default_port = DATABASE_PORTS[db_type]
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
    
    @staticmethod
    async def get_container_stats(name_or_id: str) -> dict:
        """Get container resource usage stats (CPU, memory, network, disk)"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "stats", "--no-stream", "--format", "json", name_or_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return {"error": stderr.decode()}
            
            stats_list = json.loads(stdout.decode()) if stdout.decode().strip() else []
            if stats_list and len(stats_list) > 0:
                stats = stats_list[0]
                return {
                    "container_id": stats.get("id", "")[:12],
                    "name": stats.get("name", ""),
                    "cpu_percent": stats.get("cpu_percent", "0%"),
                    "mem_usage": stats.get("mem_usage", "0B / 0B"),
                    "mem_percent": stats.get("mem_percent", "0%"),
                    "net_io": stats.get("net_io", "0B / 0B"),
                    "block_io": stats.get("block_io", "0B / 0B"),
                    "pids": stats.get("pids", 0),
                }
            return {"error": "No stats available"}
        except Exception as e:
            return {"error": f"Error getting stats: {str(e)}"}
    
    @staticmethod
    async def get_container_inspect(name_or_id: str) -> dict:
        """Get detailed container information via podman inspect"""
        try:
            result = await asyncio.create_subprocess_exec(
                "podman", "inspect", name_or_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return {"error": stderr.decode()}
            
            data = json.loads(stdout.decode())
            if data and len(data) > 0:
                container = data[0]
                # Extract useful info
                return {
                    "id": container.get("Id", "")[:12],
                    "name": container.get("Name", "").lstrip("/"),
                    "image": container.get("ImageName", ""),
                    "created": container.get("Created", ""),
                    "state": {
                        "status": container.get("State", {}).get("Status", "unknown"),
                        "running": container.get("State", {}).get("Running", False),
                        "started_at": container.get("State", {}).get("StartedAt", ""),
                        "finished_at": container.get("State", {}).get("FinishedAt", ""),
                        "exit_code": container.get("State", {}).get("ExitCode", 0),
                    },
                    "network": {
                        "ip_address": container.get("NetworkSettings", {}).get("IPAddress", ""),
                        "ports": container.get("NetworkSettings", {}).get("Ports", {}),
                    },
                    "mounts": [
                        {"source": m.get("Source"), "destination": m.get("Destination"), "mode": m.get("Mode")}
                        for m in container.get("Mounts", [])
                    ],
                    "env": [e for e in container.get("Config", {}).get("Env", []) if not e.startswith("PATH=")],
                }
            return {"error": "Container not found"}
        except Exception as e:
            return {"error": f"Error inspecting container: {str(e)}"}
    
    @staticmethod
    async def exec_command(name_or_id: str, command: list[str], timeout: float = 60.0) -> tuple[bool, str]:
        """
        Execute a command inside a container.
        Returns (success, output)
        """
        try:
            cmd = ["podman", "exec", name_or_id] + command
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                result.kill()
                return False, f"Command timed out after {timeout}s"
            
            output = stdout.decode() + stderr.decode()
            return result.returncode == 0, output
        except Exception as e:
            return False, f"Error executing command: {str(e)}"
    
    @staticmethod
    async def backup_database(
        name_or_id: str,
        db_type: DatabaseType,
        database: str,
        username: str,
        password: str,
        backup_path: str
    ) -> tuple[bool, str]:
        """
        Create a database backup using database-specific dump commands.
        Returns (success, message_or_backup_content)
        """
        try:
            # Build dump command based on database type
            if db_type == DatabaseType.POSTGRESQL:
                dump_cmd = ["pg_dump", "-U", username, database]
                env_prefix = f"PGPASSWORD={password}"
                cmd = ["podman", "exec", "-e", env_prefix, name_or_id] + dump_cmd
                
            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                dump_cmd = ["mysqldump", "-u", username, f"-p{password}", database]
                cmd = ["podman", "exec", name_or_id] + dump_cmd
                
            elif db_type == DatabaseType.MONGODB:
                # MongoDB outputs binary, use --archive for single file
                dump_cmd = ["mongodump", "--archive", "-u", username, "-p", password, "--authenticationDatabase", "admin", "-d", database]
                cmd = ["podman", "exec", name_or_id] + dump_cmd
                
            elif db_type == DatabaseType.REDIS:
                # Redis uses BGSAVE and we get the dump.rdb
                # First trigger save
                save_cmd = ["podman", "exec", name_or_id, "redis-cli", "-a", password, "BGSAVE"]
                result = await asyncio.create_subprocess_exec(
                    *save_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()
                await asyncio.sleep(2)  # Wait for save to complete
                
                # Then copy the dump file out
                cmd = ["podman", "cp", f"{name_or_id}:/data/dump.rdb", backup_path]
                result = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()
                if result.returncode == 0:
                    return True, f"Redis backup saved to {backup_path}"
                return False, stderr.decode()
            else:
                return False, f"Unsupported database type: {db_type}"
            
            # Execute dump command
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=300.0)
            except asyncio.TimeoutError:
                result.kill()
                return False, "Backup timed out after 5 minutes"
            
            if result.returncode == 0:
                # Write to backup file
                with open(backup_path, "wb") as f:
                    f.write(stdout)
                return True, f"Backup saved to {backup_path}"
            
            return False, f"Backup failed: {stderr.decode()}"
            
        except Exception as e:
            return False, f"Error creating backup: {str(e)}"
    
    @staticmethod
    async def restore_database(
        name_or_id: str,
        db_type: DatabaseType,
        database: str,
        username: str,
        password: str,
        backup_path: str
    ) -> tuple[bool, str]:
        """
        Restore a database from a backup file.
        Returns (success, message)
        """
        try:
            # Read backup file
            try:
                with open(backup_path, "rb") as f:
                    backup_data = f.read()
            except FileNotFoundError:
                return False, f"Backup file not found: {backup_path}"
            
            # Build restore command based on database type
            if db_type == DatabaseType.POSTGRESQL:
                # Copy file into container, then restore
                container_path = "/tmp/restore.sql"
                
                # Write to temp file and copy into container
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp:
                    tmp.write(backup_data)
                    tmp_path = tmp.name
                
                cp_cmd = ["podman", "cp", tmp_path, f"{name_or_id}:{container_path}"]
                result = await asyncio.create_subprocess_exec(*cp_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await result.communicate()
                
                # Restore using psql
                restore_cmd = ["podman", "exec", "-e", f"PGPASSWORD={password}", name_or_id, 
                              "psql", "-U", username, "-d", database, "-f", container_path]
                
            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                container_path = "/tmp/restore.sql"
                
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp:
                    tmp.write(backup_data)
                    tmp_path = tmp.name
                
                cp_cmd = ["podman", "cp", tmp_path, f"{name_or_id}:{container_path}"]
                result = await asyncio.create_subprocess_exec(*cp_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await result.communicate()
                
                restore_cmd = ["podman", "exec", name_or_id, 
                              "sh", "-c", f"mysql -u {username} -p{password} {database} < {container_path}"]
                
            elif db_type == DatabaseType.MONGODB:
                container_path = "/tmp/restore.archive"
                
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".archive") as tmp:
                    tmp.write(backup_data)
                    tmp_path = tmp.name
                
                cp_cmd = ["podman", "cp", tmp_path, f"{name_or_id}:{container_path}"]
                result = await asyncio.create_subprocess_exec(*cp_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await result.communicate()
                
                restore_cmd = ["podman", "exec", name_or_id, 
                              "mongorestore", "--archive=" + container_path, "-u", username, "-p", password, 
                              "--authenticationDatabase", "admin"]
                
            elif db_type == DatabaseType.REDIS:
                # Copy dump.rdb into container and restart
                cp_cmd = ["podman", "cp", backup_path, f"{name_or_id}:/data/dump.rdb"]
                result = await asyncio.create_subprocess_exec(*cp_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await result.communicate()
                
                if result.returncode != 0:
                    return False, f"Failed to copy backup: {stderr.decode()}"
                
                # Restart container to load the dump
                await ContainerService.stop_container(name_or_id)
                await asyncio.sleep(1)
                await ContainerService.start_container(name_or_id)
                
                return True, "Redis backup restored (container restarted)"
            else:
                return False, f"Unsupported database type: {db_type}"
            
            # Execute restore command
            result = await asyncio.create_subprocess_exec(
                *restore_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=300.0)
            except asyncio.TimeoutError:
                result.kill()
                return False, "Restore timed out after 5 minutes"
            
            if result.returncode == 0:
                return True, "Database restored successfully"
            
            return False, f"Restore failed: {stderr.decode()}"
            
        except Exception as e:
            return False, f"Error restoring database: {str(e)}"
    
    @staticmethod
    async def get_database_size(name_or_id: str, db_type: DatabaseType, database: str, username: str, password: str) -> dict:
        """Get the size of the database"""
        try:
            if db_type == DatabaseType.POSTGRESQL:
                cmd = ["podman", "exec", "-e", f"PGPASSWORD={password}", name_or_id,
                       "psql", "-U", username, "-d", database, "-t", "-c", 
                       f"SELECT pg_size_pretty(pg_database_size('{database}'));"]
            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                cmd = ["podman", "exec", name_or_id,
                       "mysql", "-u", username, f"-p{password}", "-N", "-e",
                       f"SELECT COALESCE(CONCAT(ROUND(SUM(data_length + index_length) / 1024 / 1024, 2), ' MB'), '0.00 MB') FROM information_schema.tables WHERE table_schema = '{database}';"]
            elif db_type == DatabaseType.MONGODB:
                cmd = ["podman", "exec", name_or_id,
                       "mongosh", "-u", username, "-p", password, "--authenticationDatabase", "admin",
                       database, "--quiet", "--eval", "JSON.stringify(db.stats())"]
            elif db_type == DatabaseType.REDIS:
                cmd = ["podman", "exec", name_or_id, "redis-cli", "-a", password, "INFO", "memory"]
            else:
                return {"error": f"Unsupported database type: {db_type}"}
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                output = stdout.decode().strip()
                if db_type == DatabaseType.REDIS:
                    # Parse Redis INFO memory output
                    for line in output.split("\n"):
                        if line.startswith("used_memory_human:"):
                            return {"size": line.split(":")[1].strip()}
                    return {"size": "unknown"}
                elif db_type == DatabaseType.MONGODB:
                    try:
                        stats = json.loads(output)
                        size_bytes = stats.get("dataSize", 0) + stats.get("indexSize", 0)
                        size_mb = round(size_bytes / 1024 / 1024, 2)
                        return {"size": f"{size_mb} MB", "raw": stats}
                    except:
                        return {"size": output}
                return {"size": output.strip()}
            
            error_msg = stderr.decode().strip()
            print(f"Error getting database size for {name_or_id}: {error_msg}")
            return {"error": error_msg if error_msg else "Unknown error"}
        except Exception as e:
            print(f"Exception getting database size: {str(e)}")
            return {"error": f"Error getting database size: {str(e)}"}
    
    @staticmethod
    async def list_database_tables(name_or_id: str, db_type: DatabaseType, database: str, username: str, password: str) -> list:
        """List all tables in the database"""
        try:
            if db_type == DatabaseType.POSTGRESQL:
                cmd = ["podman", "exec", "-e", f"PGPASSWORD={password}", name_or_id,
                       "psql", "-U", username, "-d", database, "-t", "-c",
                       "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"]
            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                cmd = ["podman", "exec", name_or_id,
                       "mysql", "-u", username, f"-p{password}", database, "-N", "-e",
                       "SHOW TABLES;"]
            elif db_type == DatabaseType.MONGODB:
                cmd = ["podman", "exec", name_or_id,
                       "mongosh", "-u", username, "-p", password, "--authenticationDatabase", "admin",
                       database, "--quiet", "--eval", "JSON.stringify(db.getCollectionNames())"]
            elif db_type == DatabaseType.REDIS:
                return []  # Redis doesn't have tables
            else:
                return []
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                output = stdout.decode().strip()
                if db_type == DatabaseType.MONGODB:
                    try:
                        tables = json.loads(output)
                        return tables if isinstance(tables, list) else []
                    except:
                        print(f"Error parsing MongoDB tables: {output}")
                        return []
                # Split by newlines and filter empty
                tables = [t.strip() for t in output.split('\n') if t.strip()]
                return tables
            
            error_msg = stderr.decode().strip()
            print(f"Error listing tables for {name_or_id}: {error_msg}")
            return []
        except Exception as e:
            print(f"Exception listing tables: {str(e)}")
            return []
    
    @staticmethod
    async def get_table_schema(name_or_id: str, db_type: DatabaseType, database: str, username: str, password: str, table_name: str) -> list:
        """Get the schema/structure of a table"""
        try:
            if db_type == DatabaseType.POSTGRESQL:
                cmd = ["podman", "exec", "-e", f"PGPASSWORD={password}", name_or_id,
                       "psql", "-U", username, "-d", database, "-c",
                       f"SELECT column_name, data_type, character_maximum_length, is_nullable FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position;"]
            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                cmd = ["podman", "exec", name_or_id,
                       "mysql", "-u", username, f"-p{password}", database, "-e",
                       f"DESCRIBE {table_name};"]
            elif db_type == DatabaseType.MONGODB:
                # MongoDB is schemaless, return sample document structure
                cmd = ["podman", "exec", name_or_id,
                       "mongosh", "-u", username, "-p", password, "--authenticationDatabase", "admin",
                       database, "--quiet", "--eval", f"JSON.stringify(db.{table_name}.findOne())"]
            else:
                return []
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                output = stdout.decode().strip()
                if db_type == DatabaseType.MONGODB:
                    try:
                        doc = json.loads(output)
                        if doc:
                            # Convert document to schema-like format
                            schema = []
                            for key, value in doc.items():
                                schema.append({
                                    "name": key,
                                    "type": type(value).__name__,
                                    "nullable": "YES"
                                })
                            return schema
                    except:
                        pass
                    return []
                
                # Parse output into structured data
                lines = output.split('\n')
                schema = []
                for line in lines[2:]:  # Skip header rows
                    if line.strip() and not line.startswith('-'):
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 2:
                            if db_type == DatabaseType.POSTGRESQL and len(parts) >= 4:
                                schema.append({
                                    "name": parts[0],
                                    "type": parts[1] + (f"({parts[2]})" if parts[2] else ""),
                                    "nullable": parts[3]
                                })
                            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                                schema.append({
                                    "name": parts[0],
                                    "type": parts[1] if len(parts) > 1 else "unknown",
                                    "nullable": parts[2] if len(parts) > 2 else "YES"
                                })
                return schema
            
            return []
        except Exception as e:
            print(f"Error getting table schema: {str(e)}")
            return []
    
    @staticmethod
    async def get_table_data(name_or_id: str, db_type: DatabaseType, database: str, username: str, password: str, table_name: str, limit: int = 10) -> dict:
        """Get sample data from a table"""
        try:
            if db_type == DatabaseType.POSTGRESQL:
                cmd = ["podman", "exec", "-e", f"PGPASSWORD={password}", name_or_id,
                       "psql", "-U", username, "-d", database, "-c",
                       f"SELECT * FROM {table_name} LIMIT {limit};"]
            elif db_type in (DatabaseType.MYSQL, DatabaseType.MARIADB):
                cmd = ["podman", "exec", name_or_id,
                       "mysql", "-u", username, f"-p{password}", database, "-e",
                       f"SELECT * FROM {table_name} LIMIT {limit};"]
            elif db_type == DatabaseType.MONGODB:
                cmd = ["podman", "exec", name_or_id,
                       "mongosh", "-u", username, "-p", password, "--authenticationDatabase", "admin",
                       database, "--quiet", "--eval", f"JSON.stringify(db.{table_name}.find().limit({limit}).toArray())"]
            else:
                return {"rows": [], "columns": []}
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                output = stdout.decode().strip()
                
                if db_type == DatabaseType.MONGODB:
                    try:
                        docs = json.loads(output)
                        if docs and len(docs) > 0:
                            columns = list(docs[0].keys())
                            rows = [[str(doc.get(col, '')) for col in columns] for doc in docs]
                            return {"rows": rows, "columns": columns}
                    except:
                        pass
                    return {"rows": [], "columns": []}
                
                # Parse tabular output
                lines = output.split('\n')
                if len(lines) < 3:
                    return {"rows": [], "columns": []}
                
                # Extract column names from header
                header = lines[0]
                columns = [col.strip() for col in header.split('|') if col.strip()]
                
                # Extract data rows
                rows = []
                for line in lines[2:]:  # Skip header and separator
                    if line.strip() and not line.startswith('-') and '(' not in line:
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= len(columns):
                            rows.append(parts[:len(columns)])
                
                return {"rows": rows[:limit], "columns": columns}
            
            return {"rows": [], "columns": []}
        except Exception as e:
            print(f"Error getting table data: {str(e)}")
            return {"rows": [], "columns": []}
container_service = ContainerService()
