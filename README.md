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

## Examples

### Node.js Development

```bash
box npm install                    # Auto-detects Node.js
box -V 18 npm test                 # Specific Node version
box -t -p 3000 npm run dev         # With tmux and port mapping
box -rw ./src npm run build        # Mount source code
```

### Python Development

```bash
box python script.py               # Auto-detects Python
box -V 3.9 python -m pytest        # Specific Python version
box -rw ./app -p 8000 python manage.py runserver
box -t python                      # Interactive with tmux
```

### Volume Mounting

```bash
box -ro ~/data/input -rw ~/data/output python process.py
box -ro ~/datasets:data -rw ~/results:output python analyze.py
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


## How It Works

1. Detects Docker or Podman runtime
2. Auto-selects container based on command or project files
3. Builds optimized image with bash/tmux if needed
4. Runs container with specified mounts and ports
5. Executes command or starts interactive shell


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