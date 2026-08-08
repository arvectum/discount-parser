#!/bin/bash
set -e
cd "$(dirname "$0")"

PYTHON="$PWD/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "Discount Parser is not installed yet."
  echo "Run install_macos.command first."
  read -r -p "Press Enter to close..."
  exit 1
fi

exec "$PYTHON" -m src.cli web
