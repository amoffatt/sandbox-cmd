# Box - CLI Container Isolation Tool

Run commands in isolated Docker/Podman containers with automatic environment detection, volume mounting, and port mapping.

## Installation

### From Source

Clone the repository and install using pip:

```bash
git clone https://github.com/amoffatt/sandbox-cmd.git
cd sandbox-cmd
pip install .
```

For development (editable installation):

```bash
pip install -e .
```

After installation, the `box` command will be available in your PATH.

## Prerequisites

- Python 3.6 or higher
- Docker or Podman installed and running

### Installing Container Runtime

#### macOS
- **Recommended**: [OrbStack](https://orbstack.dev/) - A fast, lightweight Docker Desktop alternative that uses minimal resources
- **Alternative**: [Docker Desktop](https://docs.docker.com/desktop/install/mac-install/)
- **Podman**: `brew install podman`

#### Linux
- **Docker**: Follow the [official Docker installation guide](https://docs.docker.com/engine/install/)
- **Podman**: `sudo apt install podman` (Ubuntu/Debian) or `sudo dnf install podman` (Fedora)

#### Windows
- **Docker Desktop**: [Download Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- **Podman**: [Podman Desktop for Windows](https://podman-desktop.io/)

## Usage

```bash
box [OPTIONS] [COMMAND...]
```

Box auto-detects the container environment:
- `box npm install` → Node.js container
- `box python script.py` → Python container  
- `box echo hello` → Alpine container (default)

### Options

- `--node` - Force Node.js container
- `--py` - Force Python container
- `-V VERSION` - Specify image version
- `-t, --tmux` - Run inside tmux session
- `--clean` - Remove all box-built images
- `-p PORT` - Map ports (e.g., `-p 3000` or `-p 8080:3000`)
- `-ro PATH` - Mount directory as read-only
- `-rw PATH` - Mount directory as read-write
- `-n, --name NAME` - Save this configuration as a named image
- `-i, --image NAME` - Use a previously saved named image
- `--force` - Overwrite existing named image without confirmation

**Note**: The first mounted directory becomes the working directory inside the container.

## Examples

### Node.js Development

```bash
box -rw . npm install              # Mount current directory and install
box -rw . -V 18 npm test           # Run tests with Node 18
box -rw . -t -p 3000 npm run dev   # Dev server with code access
box -rw ./src npm run build        # Mount source code for build
```

### Python Development

```bash
box -rw . python script.py         # Run script with access to current dir
box -rw . -V 3.9 python -m pytest  # Run tests with Python 3.9
box -rw ./app -p 8000 python manage.py runserver  # Django with app dir as working dir
box -rw . -t python                # Interactive Python in current dir
```

### Volume Mounting

```bash
box -ro ~/data/input -rw ~/data/output python process.py  # Working dir: ~/data/input
box -ro ~/datasets:/data -rw ~/results:/output python analyze.py  # Working dir: /data
```

### Web Development

```bash
box --node -p 3000 -rw ./my-app npm start         # React
box --node -p 3000 -p 8080 -rw . npm run dev      # Full-stack
box --py -p 5000 -rw ./flask-app python app.py    # Flask
```

### Interactive Sessions

```bash
box                                # Default Alpine shell
box --node                         # Node.js shell
box --py                           # Python shell
box -rw ~/projects -ro ~/data bash # With mounts
```

### Named Images

Save frequently used configurations for quick access:

```bash
# Create a named image with your development setup
box -n myapp --node -p 3000 -p 8080 -rw . npm run dev

# Later, run the same configuration instantly
box -i myapp

# Create a Python data science environment
box -n datasci --py -V 3.9 -rw ~/notebooks jupyter lab

# Use it anytime
box -i datasci
```

Named configurations are stored in `~/.box-cli/config.json` and automatically rebuild if the Docker image is missing.

When creating a named image with an existing name, Box will prompt for confirmation unless you use the `--force` flag:

```bash
# Prompts for confirmation if 'myapp' already exists
box -n myapp --node npm start

# Overwrites without asking
box -n myapp --force --node npm start
```


## How It Works

1. Detects Docker or Podman runtime
2. Auto-selects container based on command or project files
3. Builds optimized image with bash/tmux if needed
4. Runs container with specified mounts and ports
5. Executes command or starts interactive shell
6. Optionally saves configuration for named images in `~/.box-cli/config.json`


## Tmux Usage (`-t` flag)

- Create window: `Ctrl-b c`
- Switch windows: `Ctrl-b n/p`
- Split horizontally: `Ctrl-b %`
- Split vertically: `Ctrl-b "`
- Navigate panes: `Ctrl-b` + arrows

## Base Images

- Node.js: `node:lts` or `node:VERSION`
- Python: `python:latest` or `python:VERSION`
- Default: `alpine:latest`


## Troubleshooting

- **No Docker/Podman**: Install from [Docker](https://docs.docker.com/get-docker/) or [Podman](https://podman.io/getting-started/installation)
- **Permission errors**: Add user to `docker` group (Docker) or use rootless mode (Podman)
- **Port in use**: Map to different port with `-p 8080:3000`

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.