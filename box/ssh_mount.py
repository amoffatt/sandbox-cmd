#!/usr/bin/env python3
"""SSH mounting utilities for Box CLI"""

import shutil
import subprocess
import re
import atexit
from pathlib import Path
from typing import Optional, Tuple, List


class SSHFSManager:
    """Manage SSHFS mounts on host system using fuse-t"""
    
    def __init__(self):
        self.ssh_mounts = []  # Track SSH mount info: (local_path, remote_spec, is_mounted)
        atexit.register(self.cleanup_mounts)
    
    def check_sshfs_available(self) -> bool:
        """Check if fuse-t-sshfs is available, try to install if not found"""
        if shutil.which('sshfs') is not None:
            return True
        
        # Try to auto-install if brew is available
        if shutil.which('brew') is not None:
            print("sshfs not found. fuse-t and fuse-t-sshfs are required for SSH mounting.")
            response = input("Install via Homebrew? [Y/n]: ").strip().lower()
            
            if response in ['', 'y', 'yes']:
                print("Installing fuse-t and fuse-t-sshfs via Homebrew...")
                try:
                    # Add fuse-t tap if not already added
                    subprocess.run(['brew', 'tap', 'macos-fuse-t/homebrew-cask'], 
                                 capture_output=True, check=False)
                    
                    # Install fuse-t and fuse-t-sshfs
                    result = subprocess.run(['brew', 'install', 'fuse-t', 'fuse-t-sshfs'], 
                                          capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        print("✓ Successfully installed fuse-t and fuse-t-sshfs")
                        # Check again after installation
                        return shutil.which('sshfs') is not None
                    else:
                        print(f"✗ Failed to install fuse-t: {result.stderr}")
                        
                except Exception as e:
                    print(f"✗ Error during installation: {e}")
            else:
                print("Installation cancelled.")
        
        return False
    
    def create_ssh_mount(self, ssh_spec: str, read_only: bool = False, mount_point: Optional[str] = None) -> Optional[str]:
        """Create SSHFS mount on host and return local mount path"""
        if not self.check_sshfs_available():
            print("Error: sshfs not found and auto-installation failed.")
            print("Manual installation: brew tap macos-fuse-t/homebrew-cask && brew install fuse-t fuse-t-sshfs")
            return None
        
        user, host, remote_path = self.parse_ssh_url(ssh_spec)
        
        # Create temporary mount directory
        mount_base = Path.home() / '.box-cli' / 'ssh-mounts'
        mount_base.mkdir(parents=True, exist_ok=True)
        
        # Use provided mount point or generate unique mount point name
        if mount_point:
            local_mount_path = Path(mount_point).expanduser().resolve()
            local_mount_path.mkdir(parents=True, exist_ok=True)
        else:
            mount_name = f"{user or 'nouser'}@{host}-{remote_path.replace('/', '_')}"
            local_mount_path = mount_base / mount_name
            local_mount_path.mkdir(exist_ok=True)
        
        # Build sshfs command
        remote_target = f"{user}@{host}:{remote_path}" if user else f"{host}:{remote_path}"
        sshfs_cmd = ['sshfs', remote_target, str(local_mount_path)]
        
        # Add options for better compatibility and debugging
        sshfs_options = [
            'StrictHostKeyChecking=accept-new',
            'ConnectTimeout=10',          # Faster timeout for connection
            'ServerAliveInterval=15',     # Keep connection alive
            'ServerAliveCountMax=3',      # Max missed keepalives
            'follow_symlinks',            # Follow symbolic links
            'auto_cache',                 # Enable caching
            'kernel_cache',               # Use kernel cache
            'reconnect',                  # Auto-reconnect on connection loss
        ]
        
        # Add read-only option if specified
        if read_only:
            sshfs_options.append('ro')
        
        # Join all options
        sshfs_cmd.extend(['-o', ','.join(sshfs_options)])
        
        print(f"Mounting {remote_target} to {local_mount_path}...")
        
        try:
            # Run sshfs mount directly (it will test connectivity)
            result = subprocess.run(
                sshfs_cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                # Verify mount actually worked by testing directory access
                try:
                    # Try to list the mounted directory
                    test_result = subprocess.run(
                        ['ls', '-la', str(local_mount_path)],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if test_result.returncode == 0:
                        print(f"✓ SSH mount successful: {remote_target} -> {local_mount_path}")
                        self.ssh_mounts.append((str(local_mount_path), ssh_spec, True))
                        return str(local_mount_path)
                    else:
                        print(f"✗ SSH mount appeared to succeed but directory is not accessible")
                        print(f"  Verification error: {test_result.stderr}")
                        # Try to unmount
                        subprocess.run(['umount', str(local_mount_path)], capture_output=True)
                        return None
                        
                except subprocess.TimeoutExpired:
                    print(f"✗ SSH mount verification timed out")
                    return None
                except Exception as e:
                    print(f"✗ SSH mount verification failed: {e}")
                    return None
            else:
                print(f"✗ SSH mount failed:")
                print(f"  Command: {' '.join(sshfs_cmd)}")
                print(f"  Stderr: {result.stderr}")
                print(f"  Stdout: {result.stdout}")
                
                # Clean up empty directory
                try:
                    if not mount_point:  # Only remove auto-generated directories
                        local_mount_path.rmdir()
                except:
                    pass
                return None
                
        except subprocess.TimeoutExpired:
            print(f"✗ SSH mount timed out for {remote_target}")
            print(f"  Try running manually: {' '.join(sshfs_cmd)}")
            return None
        except Exception as e:
            print(f"✗ Error creating SSH mount: {e}")
            return None
    
    @staticmethod
    def parse_ssh_url(spec: str) -> Tuple[Optional[str], str, str]:
        """Parse SSH URL into user, host, and remote path"""
        if '@' in spec:
            user_host, remote_path = spec.rsplit(':', 1)
            user, host = user_host.split('@', 1)
        else:
            host, remote_path = spec.rsplit(':', 1)
            user = None
        return user, host, remote_path
    
    @staticmethod
    def is_ssh_url(spec: str) -> bool:
        """Check if the spec is an SSH URL"""
        # Pattern: user@host:path or host:path
        ssh_pattern = r'^([^@]+@)?[^:/@]+:[^:]+$'
        return bool(re.match(ssh_pattern, spec)) and not spec.startswith('/') and not (len(spec) > 1 and spec[1:3] == ':\\')
    
    def unmount_ssh_path(self, local_path: str) -> bool:
        """Unmount a specific SSH mount using macOS-preferred methods"""
        import platform
        
        try:
            # On macOS, try diskutil unmount first (preferred method)
            if platform.system() == 'Darwin':
                result = subprocess.run(['diskutil', 'unmount', local_path], capture_output=True, timeout=10, text=True)
                if result.returncode == 0:
                    print(f"✓ Unmounted {local_path}")
                    # Remove from tracking
                    self.ssh_mounts = [(p, r, m) for p, r, m in self.ssh_mounts if p != local_path]
                    return True
                
                # If diskutil fails, try force unmount
                result = subprocess.run(['diskutil', 'unmount', 'force', local_path], capture_output=True, timeout=10, text=True)
                if result.returncode == 0:
                    print(f"✓ Force unmounted {local_path}")
                    # Remove from tracking
                    self.ssh_mounts = [(p, r, m) for p, r, m in self.ssh_mounts if p != local_path]
                    return True
            
            # Fallback to standard umount (macOS and Linux)
            result = subprocess.run(['umount', local_path], capture_output=True, timeout=5, text=True)
            if result.returncode == 0:
                print(f"✓ Unmounted {local_path}")
                # Remove from tracking
                self.ssh_mounts = [(p, r, m) for p, r, m in self.ssh_mounts if p != local_path]
                return True
            
            # Try fusermount as last resort (Linux only)
            if shutil.which('fusermount'):
                result = subprocess.run(['fusermount', '-u', local_path], capture_output=True, timeout=5, text=True)
                if result.returncode == 0:
                    print(f"✓ Unmounted {local_path}")
                    # Remove from tracking
                    self.ssh_mounts = [(p, r, m) for p, r, m in self.ssh_mounts if p != local_path]
                    return True
            
            print(f"✗ Failed to unmount {local_path}")
            if result.stderr:
                print(f"  Error: {result.stderr.strip()}")
            return False
            
        except Exception as e:
            print(f"✗ Error unmounting {local_path}: {e}")
            return False
    
    def list_mounts(self) -> List[Tuple[str, str]]:
        """List all active SSH mounts"""
        return [(local_path, remote_spec) for local_path, remote_spec, is_mounted in self.ssh_mounts if is_mounted]
    
    def cleanup_mounts(self):
        """Clean up all SSH mounts"""
        import platform
        
        for local_path, remote_spec, is_mounted in self.ssh_mounts:
            if is_mounted:
                try:
                    # Use the same unmount logic as unmount_ssh_path
                    unmounted = False
                    
                    # On macOS, try diskutil first
                    if platform.system() == 'Darwin':
                        result = subprocess.run(['diskutil', 'unmount', local_path], 
                                             capture_output=True, timeout=5)
                        if result.returncode == 0:
                            unmounted = True
                        else:
                            # Try force unmount
                            result = subprocess.run(['diskutil', 'unmount', 'force', local_path], 
                                                 capture_output=True, timeout=5)
                            if result.returncode == 0:
                                unmounted = True
                    
                    # Fallback to standard umount
                    if not unmounted:
                        result = subprocess.run(['umount', local_path], 
                                             capture_output=True, timeout=5)
                        if result.returncode == 0:
                            unmounted = True
                    
                    # Try fusermount as last resort (Linux)
                    if not unmounted and shutil.which('fusermount'):
                        result = subprocess.run(['fusermount', '-u', local_path], 
                                             capture_output=True, timeout=5)
                        if result.returncode == 0:
                            unmounted = True
                    
                    if unmounted:
                        print(f"✓ Unmounted {remote_spec}")
                    
                except:
                    # Silent failure during cleanup
                    pass
                
                # Remove empty mount directory if it was auto-generated
                try:
                    mount_base = Path.home() / '.box-cli' / 'ssh-mounts'
                    local_path_obj = Path(local_path)
                    if local_path_obj.parent == mount_base:
                        local_path_obj.rmdir()
                except:
                    pass
        
        self.ssh_mounts.clear()