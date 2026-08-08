#!/bin/bash
set -e

cd "$(dirname "$0")"

printf '\n========================================\n'
printf 'Discount Parser - one-click launcher\n'
printf '========================================\n\n'

PYTHON="$PWD/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "[ERROR] Virtual environment not found: .venv"
  echo "Run the installation steps from docs/USER_INSTALLATION_GUIDE.md first."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "[ERROR] .env file not found."
  echo "Copy .env.example to .env and fill in Telegram settings first."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "Starting Discount Parser..."
echo "Telegram bot + scheduler will run in this window."
echo "Press Ctrl+C to stop."
echo

"$PYTHON" -m src.cli run
