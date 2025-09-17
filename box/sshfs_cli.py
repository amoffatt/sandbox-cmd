#!/usr/bin/env python3
"""box_sshfs - Standalone SSH filesystem mounting utility"""

import argparse
import sys
import signal
import subprocess
import time
from pathlib import Path
from .ssh_mount import SSHFSManager


def parse_args():
    """Parse command line arguments for box_sshfs"""
    parser = argparse.ArgumentParser(
        description='Mount remote directories over SSH using SSHFS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  box_sshfs user@host:/path/to/mount ~/local/mount     # Mount and stay running (Ctrl+C to unmount)
  box_sshfs user@host:~/project project               # Mount to ./project  
  box_sshfs --list                                     # List active mounts
  box_sshfs --unmount ~/local/mount                    # Unmount specific path
  box_sshfs --cleanup                                  # Unmount all SSH mounts

SSH Authentication:
  - Uses your existing SSH keys and SSH agent
  - Set up passwordless SSH with ssh-copy-id for convenience
  - No passwords or keys are stored by this tool

Note: When mounting, the command stays running. Press Ctrl+C to unmount and exit.
        """
    )
    
    parser.add_argument(
        'remote_spec',
        nargs='?',
        help='Remote SSH location in format user@host:path'
    )
    
    parser.add_argument(
        'local_path',
        nargs='?',
        help='Local mount point (will be created if it doesn\'t exist)'
    )
    
    parser.add_argument(
        '--read-only', '-ro',
        action='store_true',
        help='Mount as read-only'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all active SSH mounts'
    )
    
    parser.add_argument(
        '--unmount', '-u',
        metavar='PATH',
        help='Unmount specific local path'
    )
    
    parser.add_argument(
        '--cleanup', '-c',
        action='store_true',
        help='Unmount all SSH mounts managed by box'
    )
    
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Mount and exit immediately (don\'t stay running)'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for box_sshfs"""
    args = parse_args()
    
    # Initialize SSH manager
    ssh_mgr = SSHFSManager()
    
    # Handle list command
    if args.list:
        mounts = ssh_mgr.list_mounts()
        if not mounts:
            print("No active SSH mounts found.")
            return 0
        
        print("Active SSH mounts:")
        for local_path, remote_spec in mounts:
            print(f"  {remote_spec} -> {local_path}")
        return 0
    
    # Handle unmount command
    if args.unmount:
        local_path = Path(args.unmount).expanduser().resolve()
        if ssh_mgr.unmount_ssh_path(str(local_path)):
            return 0
        else:
            return 1
    
    # Handle cleanup command
    if args.cleanup:
        ssh_mgr.cleanup_mounts()
        print("All SSH mounts cleaned up.")
        return 0
    
    # Handle mount command
    if not args.remote_spec:
        print("Error: Remote specification required", file=sys.stderr)
        print("Usage: box_sshfs user@host:path [local_path]", file=sys.stderr)
        return 1
    
    # Validate SSH URL format
    if not ssh_mgr.is_ssh_url(args.remote_spec):
        print(f"Error: Invalid SSH specification '{args.remote_spec}'", file=sys.stderr)
        print("Expected format: user@host:path or host:path", file=sys.stderr)
        return 1
    
    # Determine local mount point
    if args.local_path:
        local_mount_point = args.local_path
    else:
        # Use the basename of the remote path
        _, _, remote_path = ssh_mgr.parse_ssh_url(args.remote_spec)
        local_mount_point = Path(remote_path).name
        if not local_mount_point:
            local_mount_point = "ssh_mount"
    
    # Create a new SSH manager instance for this mount
    mount_mgr = SSHFSManager()
    
    # Track the mount path for cleanup
    mount_path = None
    
    def signal_handler(signum, frame):
        """Handle Ctrl+C to unmount and exit gracefully"""
        import platform
        print("\n🛑 Received interrupt signal, unmounting...")
        if mount_path:
            # Try manual unmount using macOS-preferred method
            try:
                unmounted = False
                
                # On macOS, use diskutil first
                if platform.system() == 'Darwin':
                    result = subprocess.run(['diskutil', 'unmount', mount_path], capture_output=True, timeout=5, text=True)
                    if result.returncode == 0:
                        unmounted = True
                    else:
                        # Try force unmount if regular fails
                        result = subprocess.run(['diskutil', 'unmount', 'force', mount_path], capture_output=True, timeout=5, text=True)
                        if result.returncode == 0:
                            unmounted = True
                
                # Fallback to umount
                if not unmounted:
                    result = subprocess.run(['umount', mount_path], capture_output=True, timeout=5, text=True)
                    if result.returncode == 0:
                        unmounted = True
                
                if unmounted:
                    print("✓ Mount cleaned up successfully")
                else:
                    print("⚠️  Manual unmount failed, letting cleanup handler try...")
            except Exception:
                print("⚠️  Manual unmount failed, letting cleanup handler try...")
        sys.exit(0)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create the mount
    mount_path = mount_mgr.create_ssh_mount(
        args.remote_spec,
        read_only=args.read_only,
        mount_point=local_mount_point
    )
    
    if not mount_path:
        return 1
    
    print(f"✓ Successfully mounted {args.remote_spec} at {mount_path}")
    
    if args.daemon:
        print("✓ Running in daemon mode, mount will persist until manually unmounted")
        print(f"  To unmount: box_sshfs --unmount {mount_path}")
        return 0
    
    # Stay running and keep the mount alive
    try:
        print("📁 Mount active - Press Ctrl+C to unmount and exit")
        print(f"   Remote: {args.remote_spec}")
        print(f"   Local:  {mount_path}")
        print("")
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())