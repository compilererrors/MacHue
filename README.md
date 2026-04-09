# MacHue

CLI and TUI for local Philips Hue control via Hue Bridge API v1.

## Overview

This project includes:

- `CLI` for discovery, pairing, light control, scene handling, and config management
- `TUI` (curses) for interactive light and scene control in the terminal
- local config file for bridge IP and API token

## Technology Choice

The current implementation uses **Python** because it provides:

- fast development and simple distribution in development environments
- built-in support for CLI (`argparse`) and terminal UI (`curses`)
- no external runtime dependencies

For single-binary distribution, **Go** is a natural alternative.

## Requirements

- Python 3.10 or later
- Philips Hue Bridge on the same network

## Installation

```bash
cd /Users/viktornyberg/Workspace/MacHue
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Initial Configuration

1. Discover the bridge:

```bash
machue discover
```

2. Create a token using the bridge button (one-time step per new client):

```bash
machue --bridge-ip 192.168.1.10 pair
```

Alternatively, save an existing token:

```bash
machue login --username <TOKEN> --bridge-ip 192.168.1.10
```

Configuration file:

- path: `~/.config/machue/config.json`
- keys: `bridge_ip` and `username`

## Usage

Common commands:

```bash
machue list
machue on 1
machue off 1
machue toggle all
machue brightness 1 180
machue groups
machue scenes
machue scenes --group 1
machue scenes --name relax
machue scene <SCENE_ID>
machue config show
machue config set --username <TOKEN>
```

Start the TUI:

```bash
machue tui
# alternatively
machue-tui
```

## Testing

Run tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

## TUI Keybindings

- `Tab`: switch between `Lights` and `Scenes`
- `1` / `2`: jump directly to `Lights` / `Scenes`
- `←` / `→`: switch views
- `↑/↓` or `j/k`: move selection
- `PgUp` / `PgDn`: move one page
- `g` / `G` or `Home` / `End`: jump to top/bottom
- `Enter` or `Space`: toggle (Lights) / recall (Scenes)
- `+/-`: adjust brightness (Lights)
- `[` / `]`: resize left/right panel proportion
- `l`: switch to Lights
- `s`: switch to Scenes
- `r`: refresh data
- `q` or `Esc`: quit

## Config Commands

- `machue config show`
- `machue config set --bridge-ip 192.168.1.10 --username <TOKEN>`
- `machue config clear --username`
- `machue config clear --bridge-ip`
- `machue config clear --all`
- `machue login --username <TOKEN> --bridge-ip 192.168.1.10`

## Troubleshooting

- `Hue error: link button not pressed`: press the bridge button and run `pair` again within the time window.
- `Hue error: Missing bridge IP`: pass `--bridge-ip` or save it with `config set`.
- `Hue error: Missing username/token`: run `pair` or save a token with `login`/`config set`.
