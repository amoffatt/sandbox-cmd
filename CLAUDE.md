# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running Tests
```bash
# Run all tests with verbose output
python run_tests.py

# Run specific test file
python tests/test_config_manager.py
python tests/test_network_restrictions.py
python tests/test_named_images.py
python tests/test_mount_merging.py

# Test with coverage (if pytest installed)
python -m pytest tests/ --cov=box --cov-report=html
```

### Installation and Setup
```bash
# Development installation (editable)
pip install -e .

# Install with test dependencies
pip install -e ".[test]"

# Manual test of CLI functionality
python -m box.cli --help
python -m box.cli -l  # List named images
```

### Building and Distribution
```bash
# Build package
python setup.py sdist bdist_wheel

# Install from source
pip install .
```

## Architecture Overview

### Core Components

**box/cli.py** - Main CLI module with these key classes:
- `ConfigManager`: Handles persistent named image configurations in `~/.box-cli/config.json`
- `ContainerRuntime`: Detects and manages Docker/Podman with daemon connectivity checks
- `ImageBuilder`: Builds dynamic images with tmux/bash, handles auto-detection of Node.js/Python environments
- `VolumeMapper`: Manages local and SSH volume mounting via SSHFSManager integration
- `NetworkManager`: Handles network restrictions (--no-network, --internal-network, --http-proxy)
- `PortMapper` & `SpecParser`: Handle port mappings and argument parsing utilities

**box/ssh_mount.py** - SSH volume mounting system:
- `SSHFSManager`: Creates and manages SSHFS mounts for remote directory access
- Automatic cleanup on exit, supports both read-only and read-write mounts

**box/sshfs_cli.py** - Standalone SSH mounting CLI (`box_sshfs` command)

### Key Architecture Patterns

**Named Images**: Complete container configurations saved to JSON, allowing instant recreation of development environments. Includes command, environment, mounts, ports, and network settings.

**Auto-Detection**: CLI automatically detects project type (Node.js, Python, Alpine) based on command and file presence (package.json, requirements.txt, etc.).

**Mount Integration**: First mounted directory becomes the working directory. SSH mounts are transparently handled via SSHFS with local bind mounting.

**Network Security**: Three levels of network isolation:
- Complete isolation (`--no-network`)
- Internal-only (`--internal-network`)
- Proxy-based filtering (`--http-proxy`)

**Dual Runtime Support**: Seamlessly works with both Docker and Podman with runtime-specific error handling and daemon connectivity checks.

### Configuration Storage

- Named images: `~/.box-cli/config.json`
- SSH mount cache: `/tmp/box-sshfs-*` (auto-cleanup)
- Container naming: `box-{base-image}`, `box-named-{name}`, `box-internal` network

### Testing Strategy

Tests use Python's unittest framework (not pytest) with extensive mocking. Key areas:
- ConfigManager persistence and named image lifecycle
- Network restriction argument parsing and container integration
- SSH mount management and cleanup
- Container runtime detection and error handling

### Entry Points

The package provides two CLI commands:
- `box`: Main container isolation tool (`box.cli:main`)
- `box_sshfs`: Standalone SSH mounting utility (`box.sshfs_cli:main`)