#!/usr/bin/env python3
"""Box - CLI container isolation tool"""

import argparse
import subprocess
import sys
import shutil
import json
import re
import socket
import time
import atexit
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from .ssh_mount import SSHFSManager


class ConfigManager:
    """Manage box CLI configuration for named images"""
    
    def __init__(self):
        self.config_dir = Path.home() / '.box-cli'
        self.config_file = self.config_dir / 'config.json'
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {'images': {}}
        return {'images': {}}
    
    def _save_config(self) -> None:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save config: {e}", file=sys.stderr)
    
    def save_image_config(self, name: str, args: argparse.Namespace, force: bool = False) -> bool:
        """Save configuration for a named image
        
        Returns True if config was saved, False if user cancelled
        """
        # Check if image already exists and prompt for confirmation
        if not force and name in self.config.get('images', {}):
            existing = self.config['images'][name]
            print(f"\nWarning: Named image '{name}' already exists with configuration:")
            print(f"  Command: {' '.join(existing.get('command', [])) or '(interactive shell)'}")
            if existing.get('node'):
                print(f"  Environment: Node.js {existing.get('image_version') or 'lts'}")
            elif existing.get('py'):
                print(f"  Environment: Python {existing.get('image_version') or 'latest'}")
            else:
                print(f"  Environment: Alpine")
            if existing.get('port'):
                print(f"  Ports: {', '.join(existing['port'])}")
            if existing.get('tmux'):
                print(f"  Tmux: enabled")
            
            response = input("\nDo you want to overwrite it? [y/N]: ").strip().lower()
            if response not in ['y', 'yes']:
                print("Operation cancelled.")
                return False
        
        config_entry = {
            'command': args.command,
            'node': args.node,
            'py': args.py,
            'image_version': args.image_version,
            'tmux': args.tmux,
            'port': args.port if args.port else [],
            'read_only': args.read_only if args.read_only else [],
            'read_write': args.read_write if args.read_write else [],
            'no_network': getattr(args, 'no_network', False),
            'internal_network': getattr(args, 'internal_network', False),
            'http_proxy': getattr(args, 'http_proxy', None)
        }
        
        self.config['images'][name] = config_entry
        self._save_config()
        print(f"✓ Saved configuration for image '{name}'")
        return True
    
    def get_image_config(self, name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a named image"""
        return self.config.get('images', {}).get(name)
    
    def list_named_images(self) -> List[str]:
        """List all configured named images"""
        return list(self.config.get('images', {}).keys())
    
    def display_named_images(self) -> None:
        """Display all named images with their configurations"""
        images = self.config.get('images', {})
        
        if not images:
            print("No named images configured.")
            print("\nCreate a named image with: box -n <name> [options] [command]")
            return
        
        print("Available named images:")
        print()
        
        for name, config in images.items():
            print(f"  {name}")
            
            # Show environment
            if config.get('node'):
                version = config.get('image_version') or 'lts'
                print(f"    Environment: Node.js {version}")
            elif config.get('py'):
                version = config.get('image_version') or 'latest'
                print(f"    Environment: Python {version}")
            else:
                print(f"    Environment: Alpine")
            
            # Show ports
            ports = config.get('port', [])
            if ports:
                print(f"    Ports: {', '.join(ports)}")
            
            # Show mounts
            ro_mounts = config.get('read_only', [])
            rw_mounts = config.get('read_write', [])
            if ro_mounts:
                print(f"    Read-only mounts: {', '.join(ro_mounts)}")
            if rw_mounts:
                print(f"    Read-write mounts: {', '.join(rw_mounts)}")
            
            # Show command
            command = config.get('command', [])
            if command:
                print(f"    Command: {' '.join(command)}")
            else:
                print(f"    Command: (interactive shell)")
            
            # Show tmux
            if config.get('tmux'):
                print(f"    Tmux: enabled")

            # Show network restrictions
            if config.get('no_network'):
                print(f"    Network: disabled")
            elif config.get('internal_network'):
                print(f"    Network: internal only")
            elif config.get('http_proxy'):
                print(f"    HTTP Proxy: {config.get('http_proxy')}")

            print()
        
        print(f"Use with: box -i <name> [additional options]")


class ContainerRuntime:
    """Detect and manage container runtime (Docker or Podman)"""

    def __init__(self):
        self.runtime = self._detect_runtime()
        if not self.runtime:
            print("Error: Neither Docker nor Podman is installed.", file=sys.stderr)
            print("Please install Docker or Podman to use this tool.", file=sys.stderr)
            sys.exit(1)

        # Check if the runtime daemon is actually running
        if not self._check_daemon_running():
            self.print_daemon_not_running_error()
            sys.exit(1)

    def _detect_runtime(self) -> Optional[str]:
        """Detect available container runtime"""
        for runtime in ['docker', 'podman']:
            if shutil.which(runtime):
                return runtime
        return None

    def _check_daemon_running(self) -> bool:
        """Check if the container runtime daemon is running"""
        try:
            # Try a simple version command to test connectivity
            result = subprocess.run(
                [self.runtime, 'version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def print_daemon_not_running_error(self) -> None:
        """Print standardized error message when daemon is not running"""
        if self.runtime == 'docker':
            print(f"Error: Docker daemon is not running.", file=sys.stderr)
            print("Please start Docker Desktop or the Docker daemon to continue.", file=sys.stderr)
        else:  # podman
            print(f"Error: Podman is not running.", file=sys.stderr)
            print("Please run 'podman machine start' to start the Podman VM.", file=sys.stderr)

    def run_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute container runtime command"""
        cmd = [self.runtime] + args
        return subprocess.run(cmd)


class Args:
    """Standardized arguments container for image operations"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, name: Optional[str] = None):
        if config:
            self.node = config.get('node', False)
            self.py = config.get('py', False)
            self.image_version = config.get('image_version')
            self.tmux = config.get('tmux', False)
            self.command = config.get('command', [])
            self.name = name
            self.no_network = config.get('no_network', False)
            self.internal_network = config.get('internal_network', False)
            self.http_proxy = config.get('http_proxy')
        else:
            self.node = False
            self.py = False
            self.image_version = None
            self.tmux = False
            self.command = []
            self.name = name
            self.no_network = False
            self.internal_network = False
            self.http_proxy = None


class ImageBuilder:
    """Handle dynamic image building with tmux pre-installed"""
    
    def __init__(self, runtime: 'ContainerRuntime', config_manager: Optional['ConfigManager'] = None):
        self.runtime = runtime
        self.config_manager = config_manager
    
    def detect_container_type_from_command(self, command: List[str]) -> str:
        """Auto-detect container type based on the command"""
        if not command:
            return 'alpine'
        
        first_cmd = command[0].lower()
        
        # Node.js related commands
        node_commands = {
            'npm', 'npx', 'yarn', 'pnpm', 'node', 'nodejs',
            'webpack', 'vite', 'next', 'nuxt', 'gatsby',
            'react-scripts', 'vue-cli-service', 'ng', 'angular',
            'tsc', 'ts-node', 'eslint', 'prettier', 'jest'
        }
        
        # Python related commands
        python_commands = {
            'python', 'python3', 'pip', 'pip3', 'pipenv', 'poetry',
            'pytest', 'black', 'flake8', 'mypy', 'pylint',
            'django-admin', 'flask', 'gunicorn', 'uvicorn',
            'jupyter', 'ipython', 'conda', 'mamba'
        }
        
        # Check direct command matches
        if first_cmd in node_commands:
            return 'node'
        elif first_cmd in python_commands:
            return 'python'
        
        # Check for package.json or common Node.js files in current directory
        if first_cmd in ['bash', 'sh', 'zsh']:
            try:
                from pathlib import Path
                current_dir = Path.cwd()
                
                # Check for Node.js project indicators
                if (current_dir / 'package.json').exists() or \
                   (current_dir / 'yarn.lock').exists() or \
                   (current_dir / 'pnpm-lock.yaml').exists():
                    return 'node'
                
                # Check for Python project indicators
                if (current_dir / 'requirements.txt').exists() or \
                   (current_dir / 'pyproject.toml').exists() or \
                   (current_dir / 'setup.py').exists() or \
                   (current_dir / 'Pipfile').exists() or \
                   (current_dir / 'poetry.lock').exists():
                    return 'python'
            except Exception:
                pass
        
        # Default to alpine for unrecognized commands
        return 'alpine'
    
    def get_base_image(self, args) -> str:
        """Get the base image name"""
        # Explicit flags take precedence
        if args.node:
            version = args.image_version if args.image_version else 'lts'
            return f'node:{version}'
        elif args.py:
            version = args.image_version if args.image_version else 'latest'
            return f'python:{version}'
        
        # Auto-detect based on command
        detected_type = self.detect_container_type_from_command(args.command)
        version = args.image_version if args.image_version else None
        
        if detected_type == 'node':
            version = version or 'lts'
            return f'node:{version}'
        elif detected_type == 'python':
            version = version or 'latest'
            return f'python:{version}'
        else:
            return 'alpine:latest'
    
    def get_box_image_name(self, base_image: str, include_tmux: bool = False, custom_name: Optional[str] = None) -> str:
        """Generate box image name from base image or use custom name"""
        if custom_name:
            # Use custom name for the image
            suffix = ''
            if include_tmux:
                suffix += '-tmux'
            return f'box-named-{custom_name}{suffix}'
        else:
            # Replace : and / with - for valid image names
            safe_name = base_image.replace(':', '-').replace('/', '-')
            suffix = ''
            if include_tmux:
                suffix += '-tmux'
            return f'box-{safe_name}{suffix}'
    
    def image_exists(self, image_name: str) -> bool:
        """Check if image already exists locally"""
        return self._run_container_command(['image', 'inspect', image_name], capture_output=True)
    
    def _run_container_command(self, args: List[str], capture_output: bool = False) -> bool:
        """Run container command and return success status"""
        try:
            cmd = [self.runtime.runtime] + args
            result = subprocess.run(cmd, capture_output=capture_output, text=True)
            return result.returncode == 0
        except Exception:
            return False
    
    def _pull_base_image(self, base_image: str) -> bool:
        """Pull base image and return success status"""
        print(f"Pulling base image: {base_image}")
        success = self._run_container_command(['pull', base_image], capture_output=True)
        if not success:
            print(f"Warning: Could not pull {base_image}, trying to build anyway...")
        return success
    
    def build_dockerfile_content(self, base_image: str, include_tmux: bool = False) -> str:
        """Generate Dockerfile content for the given base image"""
        install_cmds = []
        
        if 'alpine' in base_image:
            packages = ['bash']
            if include_tmux:
                packages.append('tmux')
            install_cmds.append(f'RUN apk add --no-cache {" ".join(packages)}')
        else:
            packages = []
            if include_tmux:
                packages.append('tmux')
            
            if packages:
                install_cmds.append(f'RUN apt-get update && apt-get install -y {" ".join(packages)} && rm -rf /var/lib/apt/lists/*')
            else:
                install_cmds.append('# bash already available')
        
        return f"""FROM {base_image}
{chr(10).join(install_cmds)}
WORKDIR /root
"""
    
    def build_image(self, base_image: str, box_image_name: str, include_tmux: bool = False) -> bool:
        """Build the box image with optional tmux"""
        tools = []
        if include_tmux:
            tools.append('tmux')
        if not tools:
            tools.append('bash')
        
        print(f"Building box image with {', '.join(tools)}: {box_image_name}")
        
        dockerfile_content = self.build_dockerfile_content(base_image, include_tmux)
        
        try:
            # Build image using stdin for Dockerfile
            result = subprocess.run(
                [self.runtime.runtime, 'build', '-t', box_image_name, '-'],
                input=dockerfile_content,
                text=True,
                capture_output=True
            )
            
            if result.returncode == 0:
                print(f"✓ Successfully built {box_image_name}")
                return True
            else:
                # Check for common connection errors
                if "connection refused" in result.stderr.lower() or "cannot connect" in result.stderr.lower():
                    print("✗ ", end="", file=sys.stderr)
                    self.runtime.print_daemon_not_running_error()
                else:
                    print(f"✗ Failed to build image: {result.stderr}")
                return False
        except Exception as e:
            print(f"✗ Error building image: {e}")
            return False
    
    def get_or_build_image(self, args) -> str:
        """Get existing box image or build it if needed"""
        base_image = self.get_base_image(args)
        use_tmux = args.tmux
        custom_name = args.name if hasattr(args, 'name') else None
        box_image_name = self.get_box_image_name(base_image, use_tmux, custom_name)
        
        # Show auto-detection info if no explicit flags were used
        if not args.node and not args.py and args.command:
            detected_type = self.detect_container_type_from_command(args.command)
            if detected_type != 'alpine':
                print(f"Auto-detected {detected_type.title()} environment for command: {' '.join(args.command)}")
        
        # Check if box image already exists
        if self.image_exists(box_image_name):
            return box_image_name
        
        # Pull base image first to ensure it exists
        self._pull_base_image(base_image)
        
        # Build the box image
        if self.build_image(base_image, box_image_name, use_tmux):
            return box_image_name
        else:
            # Fallback to base image if build fails
            print(f"Falling back to base image: {base_image}")
            return base_image
    
    def clean_box_images(self) -> None:
        """Remove all box-built images"""
        try:
            # List all images with box- prefix
            result = subprocess.run(
                [self.runtime.runtime, 'images', '--filter', 'reference=box-*', '--format', '{{.Repository}}:{{.Tag}}'],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print("Failed to list box images")
                return
            
            images = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            
            if not images:
                print("No box images found to clean")
                return
            
            print(f"Found {len(images)} box images to remove:")
            for image in images:
                print(f"  - {image}")
            
            # Remove each image
            removed_count = 0
            for image in images:
                remove_result = subprocess.run(
                    [self.runtime.runtime, 'rmi', image],
                    capture_output=True
                )
                if remove_result.returncode == 0:
                    print(f"✓ Removed {image}")
                    removed_count += 1
                else:
                    print(f"✗ Failed to remove {image}")
            
            print(f"Successfully removed {removed_count}/{len(images)} images")
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def get_or_build_named_image(self, name: str, config: Dict[str, Any]) -> Optional[str]:
        """Build or retrieve a named image from configuration"""
        args = Args(config, name)
        base_image = self.get_base_image(args)
        box_image_name = self.get_box_image_name(base_image, args.tmux, name)
        
        # Check if image exists, if not build it
        if not self.image_exists(box_image_name):
            print(f"Named image '{name}' not found, rebuilding from saved configuration...")
            
            # If we have a command to run, we need to run it and commit the result
            if config.get('command'):
                return self.build_named_image_with_command(name, config, box_image_name)
            else:
                # No command, just build the base box image
                self._pull_base_image(base_image)
                
                # Build the image
                if not self.build_image(base_image, box_image_name, args.tmux):
                    return None
        
        return box_image_name
    
    def build_named_image_with_command(self, name: str, config: Dict[str, Any], target_image_name: str) -> Optional[str]:
        """Build a named image by running the saved command and committing the result"""
        # First get/build the base box image
        base_args = Args(config, None)
        base_image = self.get_base_image(base_args)
        box_base_image = self.get_box_image_name(base_image, base_args.tmux)
        
        # Build base box image if needed
        if not self.image_exists(box_base_image):
            print(f"Building base box image: {box_base_image}")
            self._pull_base_image(base_image)
            
            if not self.build_image(base_image, box_base_image, base_args.tmux):
                print(f"Failed to build base box image")
                return None
        
        # Now run the saved command in the box image and commit the result
        command = config.get('command', [])
        print(f"Running setup command: {' '.join(command)}")
        
        try:
            # Run the command in the container
            run_cmd = [
                self.runtime.runtime, 'run', '--name', f'box-build-{name}',
                box_base_image
            ] + command
            
            result = subprocess.run(run_cmd, capture_output=False)  # Show output to user
            
            if result.returncode != 0:
                print(f"Command failed with exit code {result.returncode}")
                # Clean up the container
                subprocess.run([self.runtime.runtime, 'rm', f'box-build-{name}'], capture_output=True)
                return None
            
            # Commit the container to create the named image
            print(f"Committing container to create image: {target_image_name}")
            commit_result = subprocess.run([
                self.runtime.runtime, 'commit',
                f'box-build-{name}',
                target_image_name
            ], capture_output=True)
            
            # Clean up the build container
            subprocess.run([self.runtime.runtime, 'rm', f'box-build-{name}'], capture_output=True)
            
            if commit_result.returncode != 0:
                print(f"Failed to commit container: {commit_result.stderr.decode()}")
                return None
            
            print(f"✓ Successfully created named image: {name}")
            return target_image_name
            
        except Exception as e:
            print(f"Error building named image: {e}")
            # Clean up if something went wrong
            subprocess.run([self.runtime.runtime, 'rm', f'box-build-{name}'], capture_output=True)
            return None



class VolumeMapper:
    """Handle volume mounting logic including SSH mounts"""
    
    def __init__(self, runtime: 'ContainerRuntime'):
        self.runtime = runtime
        self.sshfs_mgr = SSHFSManager()
    
    def prepare_ssh_mount(self, ssh_spec: str, read_only: bool = False) -> Optional[str]:
        """Create SSHFS mount on host and return local mount path"""
        # Extract the actual SSH part (remove container destination if present)
        if ssh_spec.count(':') > 1:
            # Has explicit destination: user@host:remote:container
            ssh_part = ssh_spec.rsplit(':', 1)[0]
        else:
            ssh_part = ssh_spec
        
        return self.sshfs_mgr.create_ssh_mount(ssh_part, read_only)
    
    
    def get_volume_args(self, args) -> Tuple[List[str], Optional[str]]:
        """Generate volume mount arguments and return first mounted directory"""
        volume_args = []
        first_mount_dest = None
        
        # Process read-only mounts
        if args.read_only:
            for ro_spec in args.read_only:
                mount_args, dest = self._process_mount_spec(ro_spec, read_only=True)
                volume_args.extend(mount_args)
                if first_mount_dest is None:
                    first_mount_dest = dest
        
        # Process read-write mounts
        if args.read_write:
            for rw_spec in args.read_write:
                mount_args, dest = self._process_mount_spec(rw_spec, read_only=False)
                volume_args.extend(mount_args)
                if first_mount_dest is None:
                    first_mount_dest = dest
        
        return volume_args, first_mount_dest
    
    def _process_mount_spec(self, spec: str, read_only: bool) -> Tuple[List[str], Optional[str]]:
        """Process a single mount specification and return volume args and destination"""
        if self.sshfs_mgr.is_ssh_url(spec):
            return self._process_ssh_mount(spec, read_only)
        else:
            return self._process_local_mount(spec, read_only)
    
    def _process_ssh_mount(self, spec: str, read_only: bool) -> Tuple[List[str], Optional[str]]:
        """Process SSH mount specification"""
        local_mount_path = self.prepare_ssh_mount(spec, read_only)
        if not local_mount_path:
            return [], None
        
        # Parse container destination
        if ':' in spec and spec.count(':') > 1:
            # Has explicit destination: user@host:remote:container
            container_dest = spec.rsplit(':', 1)[1]
        else:
            # Use remote path basename as destination
            user, host, remote_path = self.sshfs_mgr.parse_ssh_url(spec)
            container_dest = f'/root/{Path(remote_path).name}'
        
        if not container_dest.startswith('/'):
            container_dest = f'/root/{container_dest}'
        
        # Mount the local SSHFS path into container
        opts = 'ro' if read_only else 'rw'
        return ['-v', f'{local_mount_path}:{container_dest}:{opts}'], container_dest
    
    def _process_local_mount(self, spec: str, read_only: bool) -> Tuple[List[str], str]:
        """Process local mount specification"""
        src, dest, opts = SpecParser.parse_volume_spec(spec, read_only)
        return ['-v', f'{src}:{dest}:{opts}'], dest


class SpecParser:
    """Common parsing utilities for port and volume specifications"""
    
    @staticmethod
    def parse_port_spec(spec: str) -> Tuple[str, str]:
        """Parse port specification"""
        if ':' in spec:
            parts = spec.split(':', 1)
            return parts[0], parts[1]
        else:
            return spec, spec
    
    @staticmethod
    def parse_volume_spec(spec: str, read_only: bool = False) -> Tuple[str, str, str]:
        """Parse volume specification into source, destination, and options"""
        if ':' in spec and not spec.startswith('/') and not spec[1:3] == ':\\':
            # Handle src:dest syntax
            parts = spec.split(':', 1)
            src_path = Path(parts[0]).expanduser().resolve()
            dest_path = parts[1]
            if not dest_path.startswith('/'):
                # Make destination relative to home directory in container
                dest_path = f'/root/{dest_path}'
        else:
            # Use basename as destination
            src_path = Path(spec).expanduser().resolve()
            dest_name = src_path.name
            dest_path = f'/root/{dest_name}'
        
        options = 'ro' if read_only else 'rw'
        return str(src_path), dest_path, options


class PortMapper:
    """Handle port mapping logic"""
    
    @staticmethod
    def get_port_args(args) -> List[str]:
        """Generate port mapping arguments for container runtime"""
        port_args = []
        
        if args.port:
            for port_spec in args.port:
                host_port, container_port = SpecParser.parse_port_spec(port_spec)
                port_args.extend(['-p', f'{host_port}:{container_port}'])
        
        return port_args


class NetworkManager:
    """Handle container network configuration and restrictions"""

    def __init__(self, runtime: 'ContainerRuntime'):
        self.runtime = runtime
        self._internal_network_name = 'box-internal'

    def get_network_args(self, args) -> Tuple[List[str], Optional[Dict[str, str]]]:
        """Generate network arguments and environment variables for container runtime"""
        network_args = []
        env_vars = {}

        if hasattr(args, 'no_network') and args.no_network:
            # Complete network isolation
            network_args.extend(['--network', 'none'])

        elif hasattr(args, 'internal_network') and args.internal_network:
            # Internal network only (no internet access)
            self._ensure_internal_network()
            network_args.extend(['--network', self._internal_network_name])

        # Add proxy environment variables if specified
        if hasattr(args, 'http_proxy') and args.http_proxy:
            env_vars['HTTP_PROXY'] = args.http_proxy
            env_vars['HTTPS_PROXY'] = args.http_proxy
            env_vars['http_proxy'] = args.http_proxy
            env_vars['https_proxy'] = args.http_proxy

        return network_args, env_vars

    def _ensure_internal_network(self) -> None:
        """Create internal network if it doesn't exist"""
        # Check if network exists
        check_result = subprocess.run(
            [self.runtime.runtime, 'network', 'inspect', self._internal_network_name],
            capture_output=True
        )

        if check_result.returncode != 0:
            # Network doesn't exist, create it
            print(f"Creating internal network: {self._internal_network_name}")
            create_result = subprocess.run([
                self.runtime.runtime, 'network', 'create',
                '--internal',
                self._internal_network_name
            ], capture_output=True)

            if create_result.returncode != 0:
                print(f"Warning: Failed to create internal network: {create_result.stderr.decode()}")

    def format_env_args(self, env_vars: Dict[str, str]) -> List[str]:
        """Convert environment variables dict to container runtime args"""
        env_args = []
        for key, value in env_vars.items():
            env_args.extend(['-e', f'{key}={value}'])
        return env_args


def parse_args():
    """Parse command line arguments with smart command detection"""
    # First, separate flags from command
    import sys
    args = sys.argv[1:]
    
    flags = []
    command = []
    command_started = False
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        # If we've started collecting command, everything goes to command
        if command_started:
            command.append(arg)
            i += 1
            continue
        
        # Check if this is a flag
        if arg.startswith('-'):
            flags.append(arg)
            
            # Check if this flag expects a value
            if arg in ['-V', '--image-version', '-p', '--port', '-ro', '--read-only', '-rw', '--read-write', '-n', '--name', '-i', '--image', '--http-proxy']:
                # Add the next argument as the flag value
                if i + 1 < len(args) and not args[i + 1].startswith('-'):
                    i += 1
                    flags.append(args[i])
        else:
            # This is the start of the command
            command_started = True
            command.append(arg)
        
        i += 1
    
    # Parse flags using argparse
    parser = argparse.ArgumentParser(
        description='Box - Create isolated CLI sessions within Docker or Podman containers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  box npm install                          # Auto-detect and run npm install
  box -V 3.9 python script.py              # Run Python script in Python 3.9 container
  box -t -p 3000 npm start                 # Run with tmux and port 3000 mapped
  box -ro ~/data -rw ~/code bash           # Mount data as read-only, code as read-write
  box -n mydev --node -p 3000 npm start    # Create named image 'mydev' with Node.js and port 3000
  box -i mydev -rw .                       # Run previously saved 'mydev' configuration
  box -l                                   # List all available named images
  box -rw user@host:~/project bash         # Mount remote directory over SSH
  box -ro admin@server:/logs:/logs python  # Mount SSH dir to specific container path
  box -N python analyze.py                 # Run with no network access
  box --internal-network bash              # Run with internal network only (no internet)
  box --http-proxy http://proxy:3128 curl example.com  # Use HTTP proxy for requests
        """
    )
    
    # Base image selection
    image_group = parser.add_mutually_exclusive_group()
    image_group.add_argument(
        '--node',
        action='store_true',
        help='Use Node.js image (default: LTS)'
    )
    image_group.add_argument(
        '--py',
        action='store_true',
        help='Use Python image (default: latest)'
    )
    image_group.add_argument(
        '-i', '--image',
        metavar='NAME',
        help='Use a previously saved named image'
    )
    
    # Image version
    parser.add_argument(
        '-V', '--image-version',
        metavar='VERSION',
        help='Specify image version (e.g., -V 18 for Node 18, -V 3.9 for Python 3.9)'
    )
    
    # Port mapping
    parser.add_argument(
        '-p', '--port',
        action='append',
        metavar='PORT',
        help='Map port (can be specified multiple times). Format: PORT or HOST:CONTAINER'
    )
    
    # Volume mounting
    parser.add_argument(
        '-ro', '--read-only',
        action='append',
        metavar='PATH',
        help='Mount directory as read-only. Format: PATH, SRC:DEST, or user@host:remote[:dest]'
    )
    parser.add_argument(
        '-rw', '--read-write',
        action='append',
        metavar='PATH',
        help='Mount directory as read-write. Format: PATH, SRC:DEST, or user@host:remote[:dest]'
    )
    
    # Tmux option
    parser.add_argument(
        '-t', '--tmux',
        action='store_true',
        help='Run command inside tmux session for terminal multiplexing'
    )
    
    # Named image creation
    parser.add_argument(
        '-n', '--name',
        metavar='NAME',
        help='Save this configuration as a named image for future use'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing named image without confirmation'
    )
    
    # Cleanup command
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Remove all box-built images to save disk space'
    )
    
    # List named images
    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='List all available named images'
    )

    # Network restriction options
    network_group = parser.add_mutually_exclusive_group()
    network_group.add_argument(
        '-N', '--no-network',
        action='store_true',
        help='Run container with no network access (--network none)'
    )
    network_group.add_argument(
        '--internal-network',
        action='store_true',
        help='Run container on internal network (no internet access)'
    )

    # Proxy configuration
    parser.add_argument(
        '--http-proxy',
        metavar='URL',
        help='Use HTTP proxy for container network access (e.g., http://proxy:3128)'
    )

    # Parse just the flags
    parsed_args = parser.parse_args(flags)
    
    # Add the command manually
    parsed_args.command = command
    
    return parsed_args








def main():
    """Main entry point"""
    args = parse_args()
    
    # Initialize container runtime
    runtime = ContainerRuntime()
    
    # Initialize config manager
    config_manager = ConfigManager()
    
    # Initialize image builder with config manager
    image_builder = ImageBuilder(runtime, config_manager)
    
    # Initialize volume mapper
    volume_mapper = VolumeMapper(runtime)

    # Initialize network manager
    network_manager = NetworkManager(runtime)

    # Check if we need SSH mounts
    has_ssh_mounts = False
    if args.read_only:
        has_ssh_mounts = any(SSHFSManager.is_ssh_url(spec) for spec in args.read_only)
    if not has_ssh_mounts and args.read_write:
        has_ssh_mounts = any(SSHFSManager.is_ssh_url(spec) for spec in args.read_write)
    
    # Handle cleanup command
    if args.clean:
        image_builder.clean_box_images()
        sys.exit(0)
    
    # Handle list command
    if args.list:
        config_manager.display_named_images()
        sys.exit(0)
    
    # Check if we're creating a named image and handle confirmation early
    if hasattr(args, 'name') and args.name:
        force = hasattr(args, 'force') and args.force
        
        # Auto-detect environment from command if not explicitly specified
        if not args.node and not args.py and args.command:
            detected_type = image_builder.detect_container_type_from_command(args.command)
            if detected_type == 'node':
                args.node = True
            elif detected_type == 'python':
                args.py = True
        
        if not config_manager.save_image_config(args.name, args, force=force):
            # User cancelled the operation
            sys.exit(0)
        
        # If we have a command, build the named image immediately by running the command
        if args.command:
            print(f"Building named image '{args.name}' by running setup command...")
            
            # Create config dict from args
            config = {
                'command': args.command,
                'node': args.node,
                'py': args.py,
                'image_version': args.image_version,
                'tmux': args.tmux,
                'port': args.port if args.port else [],
                'read_only': args.read_only if args.read_only else [],
                'read_write': args.read_write if args.read_write else []
            }
            
            # Generate the target image name
            base_image = image_builder.get_base_image(args)
            target_image_name = image_builder.get_box_image_name(base_image, args.tmux, args.name)
            
            # Build the named image with the command
            if image_builder.build_named_image_with_command(args.name, config, target_image_name):
                print(f"✓ Named image '{args.name}' is ready!")
                print(f"Use with: box -i {args.name} [new-command]")
                sys.exit(0)
            else:
                print(f"✗ Failed to create named image '{args.name}'")
                sys.exit(1)
        else:
            print(f"Named image '{args.name}' configuration saved.")
            print(f"Use with: box -i {args.name}")
    
    # Handle named image usage
    if hasattr(args, 'image') and args.image:
        # Load configuration for named image
        config = config_manager.get_image_config(args.image)
        if not config:
            print(f"Error: No configuration found for image '{args.image}'", file=sys.stderr)
            print(f"Available named images: {', '.join(config_manager.list_named_images()) or 'none'}", file=sys.stderr)
            sys.exit(1)
        
        # Build/get the named image
        image = image_builder.get_or_build_named_image(args.image, config)
        if not image:
            print(f"Error: Failed to build named image '{args.image}'", file=sys.stderr)
            sys.exit(1)
        
        # Apply configuration to args (but allow command override)
        args.tmux = config.get('tmux', False)
        args.port = config.get('port', [])
        
        # Merge saved mounts with any new ones provided by user
        saved_ro = config.get('read_only', [])
        saved_rw = config.get('read_write', [])
        
        # Combine saved mounts with new user-provided mounts
        if args.read_only:
            args.read_only = saved_ro + args.read_only
        else:
            args.read_only = saved_ro
            
        if args.read_write:
            args.read_write = saved_rw + args.read_write
        else:
            args.read_write = saved_rw
        
        # Apply saved network configuration (only if not overridden by user)
        if not hasattr(args, 'no_network') or not args.no_network:
            args.no_network = config.get('no_network', False)
        if not hasattr(args, 'internal_network') or not args.internal_network:
            args.internal_network = config.get('internal_network', False)
        if not hasattr(args, 'http_proxy') or not args.http_proxy:
            args.http_proxy = config.get('http_proxy')

        # Only use saved command if no command was provided by user
        if not args.command:
            args.command = config.get('command', [])
    else:
        # Get/build the image normally, including sshfs if needed
        image = image_builder.get_or_build_image(args)
    
    # Build container run command
    run_args = ['run', '--rm', '-it']
    
    # Add volume mounts and get first mounted directory
    volume_args, first_mount_dir = volume_mapper.get_volume_args(args)
    run_args.extend(volume_args)
    
    # Add port mappings
    run_args.extend(PortMapper.get_port_args(args))

    # Add network configuration
    network_args, env_vars = network_manager.get_network_args(args)
    run_args.extend(network_args)

    # Add environment variables for proxy support
    if env_vars:
        run_args.extend(network_manager.format_env_args(env_vars))

    # Add image
    run_args.append(image)
    
    # Set working directory if we have mounts (but let container handle it to avoid -w issues)
    # We'll use cd in the command instead of -w flag for better compatibility
    
    # Add command execution
    if args.tmux:
        if args.command:
            # For commands, run them in tmux with working directory
            inner_command = ' '.join(args.command)
            if first_mount_dir:
                bash_cmd = f'cd {first_mount_dir} 2>/dev/null || cd /root; tmux new-session -s main -n box "{inner_command}"'
            else:
                bash_cmd = f'tmux new-session -s main -n box "{inner_command}"'
            run_args.extend(['/bin/bash', '-c', bash_cmd])
        else:
            # For interactive shells, start tmux with bash
            if first_mount_dir:
                bash_cmd = f'cd {first_mount_dir} 2>/dev/null || cd /root; tmux new-session -s main -n box'
            else:
                bash_cmd = 'tmux new-session -s main -n box'
            run_args.extend(['/bin/bash', '-c', bash_cmd])
    else:
        # Run directly without tmux
        if args.command:
            # Execute the command directly with working directory
            if first_mount_dir:
                bash_cmd = f'cd {first_mount_dir} 2>/dev/null || cd /root; ' + ' '.join(args.command)
                run_args.extend(['/bin/bash', '-c', bash_cmd])
            else:
                run_args.extend(args.command)
        else:
            # Start an interactive bash shell
            if first_mount_dir:
                bash_cmd = f'cd {first_mount_dir} 2>/dev/null || cd /root; exec /bin/bash'
                run_args.extend(['/bin/bash', '-c', bash_cmd])
            else:
                run_args.extend(['/bin/bash'])
    
    # Execute container
    try:
        result = runtime.run_command(run_args)
        return_code = result.returncode
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return_code = 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return_code = 1
    finally:
        # Clean up SSH mounts
        if 'volume_mapper' in locals() and hasattr(volume_mapper, 'sshfs_mgr'):
            volume_mapper.sshfs_mgr.cleanup_mounts()
    
    sys.exit(return_code)


if __name__ == '__main__':
    main()