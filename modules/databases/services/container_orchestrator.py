import asyncio
import json
import logging
from typing import Optional
from .adapters import get_adapter
from .adapters.base import ContainerConfig

logger = logging.getLogger("uvicorn.error")


class ContainerOrchestrator:
    """Podman container orchestration service for database instances."""

    @staticmethod
    async def _run_command(
        cmd: list[str],
        timeout: float = 30.0,
        check: bool = True
    ) -> tuple[bool, str, str]:
        """
        Run a command with asyncio subprocess.
        
        Returns (success, stdout, stderr)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            stdout = stdout_bytes.decode().strip()
            stderr = stderr_bytes.decode().strip()
            
            success = proc.returncode == 0
            
            if check and not success:
                logger.error(f"Command failed: {' '.join(cmd)}\nstderr: {stderr}")
                
            return (success, stdout, stderr)
            
        except asyncio.TimeoutError:
            logger.error(f"Command timeout after {timeout}s: {' '.join(cmd)}")
            return (False, "", f"Command timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Command error: {' '.join(cmd)}\n{e}")
            return (False, "", str(e))

    @staticmethod
    async def check_podman_installed() -> tuple[bool, Optional[str]]:
        """Check if Podman is installed and return version."""
        success, stdout, _ = await ContainerOrchestrator._run_command(
            ["podman", "--version"],
            check=False
        )
        
        if success:
            # Output format: "podman version 4.3.1"
            return (True, stdout)
        return (False, None)

    @staticmethod
    async def get_podman_info() -> dict:
        """Get Podman system information."""
        success, stdout, _ = await ContainerOrchestrator._run_command(
            ["podman", "info", "--format", "json"]
        )
        
        if success:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse podman info JSON: {e}")
                return {}
        return {}

    @staticmethod
    async def install_podman() -> tuple[bool, str]:
        """Attempt to install Podman using apt or dnf."""
        # Try apt first (Debian/Ubuntu)
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["sudo", "apt", "update"],
            check=False
        )
        
        if success:
            success, stdout, stderr = await ContainerOrchestrator._run_command(
                ["sudo", "apt", "install", "-y", "podman"],
                timeout=300.0,
                check=False
            )
            if success:
                return (True, "Podman installed via apt")
        
        # Try dnf (Fedora/RHEL)
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["sudo", "dnf", "install", "-y", "podman"],
            timeout=300.0,
            check=False
        )
        
        if success:
            return (True, "Podman installed via dnf")
        
        return (False, "Failed to install Podman via apt or dnf")

    @staticmethod
    async def create_container(
        container_name: str,
        adapter_config: ContainerConfig,
        host_port: int,
        external_access: bool,
        memory_mb: int,
        cpu: float,
        sku: str,
        vnet_bridge: Optional[str] = None,
        vnet_ip: Optional[str] = None,
        volume_paths: Optional[dict] = None,
        secrets_paths: Optional[dict] = None
    ) -> str:
        """
        Create and start a database container with full configuration.
        
        Returns container_id (first 12 chars).
        """
        cmd = [
            "podman", "run", "-d",
            "--name", container_name,
            
            # Resource limits
            f"--memory={memory_mb}m",
            f"--cpus={cpu}",
            
            # Security flags
            "--cap-drop=all",
            "--security-opt=no-new-privileges",
            "--pids-limit=100",
        ]
        
        # Add adapter-specific capabilities
        for cap in adapter_config.capabilities:
            cmd.extend(["--cap-add", cap])
        
        # SKU-specific performance flags
        sku_series = sku[0].upper() if sku else "D"
        
        if sku_series == "B":  # Burstable
            cmd.extend(["--cpu-shares=512"])
        elif sku_series == "D":  # General purpose
            cmd.extend(["--cpu-shares=1024"])
        elif sku_series == "E":  # Memory optimized
            cmd.extend([
                "--cpu-shares=1024",
                "--memory-swappiness=0",
                "--oom-score-adj=-500"
            ])
        elif sku_series == "F":  # Compute optimized
            cmd.extend([
                "--cpu-shares=2048",
                f"--memory-swap={memory_mb}m"
            ])
        
        # Network configuration
        if vnet_bridge and vnet_ip:
            # VNet mode
            cmd.extend([
                "--network", vnet_bridge,
                "--ip", vnet_ip
            ])
        else:
            # Port mapping mode
            bind_ip = "0.0.0.0" if external_access else "127.0.0.1"
            cmd.extend(["-p", f"{bind_ip}:{host_port}:{adapter_config.port}"])
        
        # Volume mounts from adapter config
        for vol in adapter_config.volumes:
            host_path = vol["host"]
            container_path = vol["container"]
            # Add SELinux label for proper permissions
            cmd.extend(["-v", f"{host_path}:{container_path}:Z"])
        
        # Additional volume paths
        if volume_paths:
            for host_path, container_path in volume_paths.items():
                cmd.extend(["-v", f"{host_path}:{container_path}:Z"])
        
        # Secrets mount (read-only)
        if secrets_paths:
            for host_path, container_path in secrets_paths.items():
                cmd.extend(["-v", f"{host_path}:{container_path}:Z,ro"])
        
        # TLS certificate mounts (if paths exist)
        # Adapter config should include these in volumes if needed
        
        # Environment variables
        for key, value in adapter_config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])
        
        # Health check
        if adapter_config.health_check:
            hc = adapter_config.health_check
            cmd.extend([
                "--health-cmd", hc["test"],
                "--health-interval", hc.get("interval", "30s"),
                "--health-timeout", hc.get("timeout", "10s"),
                "--health-retries", str(hc.get("retries", 3))
            ])
        
        # Container image
        cmd.append(adapter_config.image)
        
        # Command override
        if adapter_config.command:
            cmd.extend(adapter_config.command)
        
        # Execute with extended timeout for image pull
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            cmd,
            timeout=300.0
        )
        
        if success:
            # Return first 12 chars of container ID
            container_id = stdout[:12]
            logger.info(f"Created container {container_name} ({container_id})")
            return container_id
        else:
            raise RuntimeError(f"Failed to create container: {stderr}")

    @staticmethod
    async def start_container(name_or_id: str) -> bool:
        """Start a stopped container."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "start", name_or_id]
        )
        
        if success:
            logger.info(f"Started container {name_or_id}")
        return success

    @staticmethod
    async def stop_container(name_or_id: str) -> bool:
        """Stop a running container."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "stop", name_or_id],
            timeout=60.0
        )
        
        if success:
            logger.info(f"Stopped container {name_or_id}")
        return success

    @staticmethod
    async def restart_container(name_or_id: str) -> bool:
        """Restart a container."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "restart", name_or_id],
            timeout=60.0
        )
        
        if success:
            logger.info(f"Restarted container {name_or_id}")
        return success

    @staticmethod
    async def remove_container(name_or_id: str, force: bool = False) -> bool:
        """Remove a container."""
        cmd = ["podman", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(name_or_id)
        
        success, stdout, stderr = await ContainerOrchestrator._run_command(cmd)
        
        if success:
            logger.info(f"Removed container {name_or_id}")
        return success

    @staticmethod
    async def get_container_status(name_or_id: str) -> str:
        """Get container status (running, stopped, etc.)."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "inspect", "--format", "{{.State.Status}}", name_or_id],
            check=False
        )
        
        if success:
            return stdout
        return "unknown"

    @staticmethod
    async def get_container_logs(
        name_or_id: str,
        lines: int = 100,
        timestamps: bool = True
    ) -> str:
        """Get container logs."""
        cmd = ["podman", "logs", "--tail", str(lines)]
        if timestamps:
            cmd.append("--timestamps")
        cmd.append(name_or_id)
        
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            cmd,
            check=False
        )
        
        return stdout if success else stderr

    @staticmethod
    async def exec_command(
        name_or_id: str,
        command: list[str],
        timeout: float = 60.0
    ) -> tuple[bool, str]:
        """Execute a command inside a running container."""
        cmd = ["podman", "exec", name_or_id] + command
        
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            cmd,
            timeout=timeout,
            check=False
        )
        
        output = stdout if success else stderr
        return (success, output)

    @staticmethod
    async def get_container_stats(name_or_id: str) -> dict:
        """Get container resource usage statistics."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "stats", "--no-stream", "--format", "json", name_or_id],
            check=False
        )
        
        if success:
            try:
                # Podman stats returns a JSON array
                stats_list = json.loads(stdout)
                if stats_list:
                    return stats_list[0]
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse stats JSON: {e}")
        
        return {}

    @staticmethod
    async def get_container_inspect(name_or_id: str) -> dict:
        """Get detailed container information."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "inspect", name_or_id],
            check=False
        )
        
        if success:
            try:
                inspect_list = json.loads(stdout)
                if inspect_list:
                    raw = inspect_list[0]
                    # Extract useful fields
                    return {
                        "id": raw.get("Id", "")[:12],
                        "name": raw.get("Name", ""),
                        "status": raw.get("State", {}).get("Status", "unknown"),
                        "running": raw.get("State", {}).get("Running", False),
                        "created": raw.get("Created", ""),
                        "started": raw.get("State", {}).get("StartedAt", ""),
                        "finished": raw.get("State", {}).get("FinishedAt", ""),
                        "exit_code": raw.get("State", {}).get("ExitCode", 0),
                        "image": raw.get("Image", ""),
                        "ports": raw.get("NetworkSettings", {}).get("Ports", {}),
                        "ip_address": raw.get("NetworkSettings", {}).get("IPAddress", ""),
                        "networks": raw.get("NetworkSettings", {}).get("Networks", {}),
                    }
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse inspect JSON: {e}")
        
        return {}

    @staticmethod
    async def list_containers(container_names: list[str] = None) -> list[dict]:
        """
        List containers, optionally filtered by names.
        
        Returns list of container info dicts.
        """
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "ps", "-a", "--format", "json"],
            check=False
        )
        
        if not success:
            return []
        
        try:
            containers = json.loads(stdout)
            
            # Filter by names if provided
            if container_names:
                containers = [
                    c for c in containers
                    if any(name in c.get("Names", []) for name in container_names)
                ]
            
            # Simplify output
            result = []
            for c in containers:
                result.append({
                    "id": c.get("Id", "")[:12],
                    "names": c.get("Names", []),
                    "image": c.get("Image", ""),
                    "status": c.get("State", "unknown"),
                    "created": c.get("Created", ""),
                    "ports": c.get("Ports", []),
                })
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ps JSON: {e}")
            return []

    @staticmethod
    async def copy_to_container(
        name_or_id: str,
        src_path: str,
        dest_path: str
    ) -> bool:
        """Copy file/directory from host to container."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "cp", src_path, f"{name_or_id}:{dest_path}"],
            timeout=120.0
        )
        
        if success:
            logger.info(f"Copied {src_path} to {name_or_id}:{dest_path}")
        return success

    @staticmethod
    async def copy_from_container(
        name_or_id: str,
        src_path: str,
        dest_path: str
    ) -> bool:
        """Copy file/directory from container to host."""
        success, stdout, stderr = await ContainerOrchestrator._run_command(
            ["podman", "cp", f"{name_or_id}:{src_path}", dest_path],
            timeout=120.0
        )
        
        if success:
            logger.info(f"Copied {name_or_id}:{src_path} to {dest_path}")
        return success
