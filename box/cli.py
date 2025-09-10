#!/usr/bin/env python3
"""Box - CLI container isolation tool"""

import argparse
import subprocess
import sys
import shutil
from pathlib import Path
from typing import List, Optional, Tuple


class ContainerRuntime:
    """Detect and manage container runtime (Docker or Podman)"""
    
    def __init__(self):
        self.runtime = self._detect_runtime()
        if not self.runtime:
            print("Error: Neither Docker nor Podman is installed.", file=sys.stderr)
            print("Please install Docker or Podman to use this tool.", file=sys.stderr)
            sys.exit(1)
    
    def _detect_runtime(self) -> Optional[str]:
        """Detect available container runtime"""
        for runtime in ['docker', 'podman']:
            if shutil.which(runtime):
                return runtime
        return None
    
    def run_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute container runtime command"""
        cmd = [self.runtime] + args
        return subprocess.run(cmd)


class ImageBuilder:
    """Handle dynamic image building with tmux pre-installed"""
    
    def __init__(self, runtime: 'ContainerRuntime'):
        self.runtime = runtime
    
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
    
    def get_box_image_name(self, base_image: str, include_tmux: bool = False) -> str:
        """Generate box image name from base image"""
        # Replace : and / with - for valid image names
        safe_name = base_image.replace(':', '-').replace('/', '-')
        suffix = '-tmux' if include_tmux else ''
        return f'box-{safe_name}{suffix}'
    
    def image_exists(self, image_name: str) -> bool:
        """Check if image already exists locally"""
        try:
            result = subprocess.run(
                [self.runtime.runtime, 'image', 'inspect', image_name],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def build_dockerfile_content(self, base_image: str, include_tmux: bool = False) -> str:
        """Generate Dockerfile content for the given base image"""
        if include_tmux:
            if 'alpine' in base_image:
                install_cmd = 'RUN apk add --no-cache tmux bash'
            else:
                install_cmd = 'RUN apt-get update && apt-get install -y tmux && rm -rf /var/lib/apt/lists/*'
        else:
            # Just ensure bash is available for non-alpine images
            if 'alpine' in base_image:
                install_cmd = 'RUN apk add --no-cache bash'
            else:
                install_cmd = '# bash already available'
        
        return f"""FROM {base_image}
{install_cmd}
WORKDIR /root
"""
    
    def build_image(self, base_image: str, box_image_name: str, include_tmux: bool = False) -> bool:
        """Build the box image with optional tmux"""
        tools = "with tmux" if include_tmux else "with bash"
        print(f"Building box image {tools}: {box_image_name}")
        
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
                print(f"✗ Failed to build image: {result.stderr}")
                return False
        except Exception as e:
            print(f"✗ Error building image: {e}")
            return False
    
    def get_or_build_image(self, args) -> str:
        """Get existing box image or build it if needed"""
        base_image = self.get_base_image(args)
        use_tmux = args.tmux
        box_image_name = self.get_box_image_name(base_image, use_tmux)
        
        # Show auto-detection info if no explicit flags were used
        if not args.node and not args.py and args.command:
            detected_type = self.detect_container_type_from_command(args.command)
            if detected_type != 'alpine':
                print(f"Auto-detected {detected_type.title()} environment for command: {' '.join(args.command)}")
        
        # Check if box image already exists
        if self.image_exists(box_image_name):
            return box_image_name
        
        # Pull base image first to ensure it exists
        print(f"Pulling base image: {base_image}")
        pull_result = subprocess.run(
            [self.runtime.runtime, 'pull', base_image],
            capture_output=True
        )
        
        if pull_result.returncode != 0:
            print(f"Warning: Could not pull {base_image}, trying to build anyway...")
        
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


class VolumeMapper:
    """Handle volume mounting logic"""
    
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
    
    @staticmethod
    def get_volume_args(args) -> Tuple[List[str], Optional[str]]:
        """Generate volume mount arguments and return first mounted directory"""
        volume_args = []
        first_mount_dest = None
        
        # Process read-only mounts
        if args.read_only:
            for ro_spec in args.read_only:
                src, dest, opts = VolumeMapper.parse_volume_spec(ro_spec, read_only=True)
                volume_args.extend(['-v', f'{src}:{dest}:{opts}'])
                if first_mount_dest is None:
                    first_mount_dest = dest
        
        # Process read-write mounts
        if args.read_write:
            for rw_spec in args.read_write:
                src, dest, opts = VolumeMapper.parse_volume_spec(rw_spec, read_only=False)
                volume_args.extend(['-v', f'{src}:{dest}:{opts}'])
                if first_mount_dest is None:
                    first_mount_dest = dest
        
        return volume_args, first_mount_dest


class PortMapper:
    """Handle port mapping logic"""
    
    @staticmethod
    def parse_port_spec(spec: str) -> Tuple[str, str]:
        """Parse port specification"""
        if ':' in spec:
            parts = spec.split(':', 1)
            return parts[0], parts[1]
        else:
            return spec, spec
    
    @staticmethod
    def get_port_args(args) -> List[str]:
        """Generate port mapping arguments for container runtime"""
        port_args = []
        
        if args.port:
            for port_spec in args.port:
                host_port, container_port = PortMapper.parse_port_spec(port_spec)
                port_args.extend(['-p', f'{host_port}:{container_port}'])
        
        return port_args


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
            if arg in ['-V', '--image-version', '-p', '--port', '-ro', '--read-only', '-rw', '--read-write']:
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
        help='Mount directory as read-only. Format: PATH or SRC:DEST'
    )
    parser.add_argument(
        '-rw', '--read-write',
        action='append',
        metavar='PATH',
        help='Mount directory as read-write. Format: PATH or SRC:DEST'
    )
    
    # Tmux option
    parser.add_argument(
        '-t', '--tmux',
        action='store_true',
        help='Run command inside tmux session for terminal multiplexing'
    )
    
    # Cleanup command
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Remove all box-built images to save disk space'
    )
    
    # Parse just the flags
    parsed_args = parser.parse_args(flags)
    
    # Add the command manually
    parsed_args.command = command
    
    return parsed_args


def build_startup_script(first_mount_dir: Optional[str], user_command: List[str], use_tmux: bool = False) -> str:
    """Build the startup script for the container"""
    # Build the startup script
    script_parts = []
    
    # Change to mounted directory if specified
    if first_mount_dir:
        script_parts.append(f'cd {first_mount_dir} 2>/dev/null || true')
    
    if use_tmux:
        # Start tmux with the command - tmux is installed in tmux-enabled images
        if user_command:
            # For commands, run them in tmux
            inner_command = ' '.join(user_command)
            script_parts.append(f'tmux new-session -s main -n box "{inner_command}"')
        else:
            # For interactive shells, start tmux with bash
            script_parts.append('tmux new-session -s main -n box')
    else:
        # Run directly without tmux
        if user_command:
            # Execute the command directly
            script_parts.append(' '.join(user_command))
        else:
            # Start an interactive bash shell
            script_parts.append('exec /bin/bash')
    
    return ' && '.join(script_parts)






def main():
    """Main entry point"""
    args = parse_args()
    
    # Initialize container runtime
    runtime = ContainerRuntime()
    
    # Initialize image builder
    image_builder = ImageBuilder(runtime)
    
    # Handle cleanup command
    if args.clean:
        image_builder.clean_box_images()
        sys.exit(0)
    
    # Get/build the image
    image = image_builder.get_or_build_image(args)
    
    # Build container run command
    run_args = ['run', '--rm', '-it']
    
    # Add volume mounts and get first mounted directory
    volume_args, first_mount_dir = VolumeMapper.get_volume_args(args)
    run_args.extend(volume_args)
    
    # Add port mappings
    run_args.extend(PortMapper.get_port_args(args))
    
    # Set working directory to /root (or first mount if available)
    if first_mount_dir:
        run_args.extend(['-w', first_mount_dir])
    else:
        run_args.extend(['-w', '/root'])
    
    # Add image
    run_args.append(image)
    
    # Build and add the startup script
    startup_script = build_startup_script(first_mount_dir, args.command, args.tmux)
    run_args.extend(['/bin/bash', '-c', startup_script])
    
    # Execute container
    try:
        result = runtime.run_command(run_args)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()