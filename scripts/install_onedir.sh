#!/usr/bin/env bash
set -euo pipefail

# Build standalone onedir bundles and install wrappers in a selected bin path.
# Output binaries:
#   dist/machue/machue
#   dist/machue-tui/machue-tui

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEFAULT_BIN_DIR="$HOME/bin"

echo "Select install path for wrapper commands:"
echo "  1) $DEFAULT_BIN_DIR (default)"
echo "  2) Enter custom path"
read -r -p "Choice [1/2] (default: 1): " INSTALL_CHOICE

if [[ -z "${INSTALL_CHOICE:-}" || "$INSTALL_CHOICE" == "1" ]]; then
  BIN_DIR="$DEFAULT_BIN_DIR"
elif [[ "$INSTALL_CHOICE" == "2" ]]; then
  read -r -p "Enter install path: " CUSTOM_BIN_DIR
  if [[ -z "${CUSTOM_BIN_DIR:-}" ]]; then
    echo "Custom path cannot be empty."
    exit 1
  fi
  BIN_DIR="${CUSTOM_BIN_DIR/#\~/$HOME}"
else
  echo "Invalid choice: $INSTALL_CHOICE"
  exit 1
fi

APP_ROOT="$BIN_DIR/.machue-apps"

if [[ ! -x ".venv/bin/python3" ]]; then
  echo "Missing .venv. Create it first:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  python3 -m pip install -e ."
  exit 1
fi

PYTHON=".venv/bin/python3"

"$PYTHON" -m pip install -e .
"$PYTHON" -m pip install pyinstaller

PYTHONPYCACHEPREFIX=/tmp/machue-pyc "$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name machue \
  machue/cli.py

PYTHONPYCACHEPREFIX=/tmp/machue-pyc "$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name machue-tui \
  machue/tui.py

mkdir -p "$BIN_DIR" "$APP_ROOT"
rm -rf "$APP_ROOT/machue" "$APP_ROOT/machue-tui"
cp -R dist/machue "$APP_ROOT/"
cp -R dist/machue-tui "$APP_ROOT/"

cat > "$BIN_DIR/machue" <<EOF
#!/usr/bin/env sh
exec "$APP_ROOT/machue/machue" "\$@"
EOF

cat > "$BIN_DIR/machue-tui" <<EOF
#!/usr/bin/env sh
exec "$APP_ROOT/machue-tui/machue-tui" "\$@"
EOF

chmod +x "$BIN_DIR/machue" "$BIN_DIR/machue-tui"

echo ""
echo "Installed:"
echo "  $BIN_DIR/machue"
echo "  $BIN_DIR/machue-tui"
echo ""
echo "Run:"
echo "  $BIN_DIR/machue --help"
echo "  $BIN_DIR/machue-tui --help"
echo ""
echo "If needed, add to PATH:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
echo ""
echo "Config path remains:"
echo "  ~/.config/machue/config.json"
