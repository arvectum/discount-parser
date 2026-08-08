#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "========================================"
echo "Discount Parser - installation"
echo "========================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] Python 3.11+ was not found."
  echo "Install Python 3.11 or newer from python.org and run this installer again."
  read -r -p "Press Enter to close..."
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || {
  echo "[ERROR] Python 3.11 or newer is required."
  read -r -p "Press Enter to close..."
  exit 1
}

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

PYTHON="$PWD/.venv/bin/python"

echo "Installing application dependencies..."
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e '.[dev]'

echo "Preparing database..."
"$PWD/.venv/bin/alembic" upgrade head

chmod +x "$PWD/start_web_macos.command" "$PWD/install_macos.command" 2>/dev/null || true

DESKTOP="$HOME/Desktop"
SHORTCUT="$DESKTOP/Discount Parser.command"
mkdir -p "$DESKTOP"
cat > "$SHORTCUT" <<EOF
#!/bin/bash
cd $(printf '%q' "$PWD")
exec ./start_web_macos.command
EOF
chmod +x "$SHORTCUT"

echo
echo "========================================"
echo "Installation completed successfully."
echo "A shortcut named 'Discount Parser.command' was created on the Desktop."
echo "Double-click it to open the web interface."
echo "========================================"
echo
read -r -p "Press Enter to close..."
