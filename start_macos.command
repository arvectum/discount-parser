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

osascript <<EOF
 tell application "Terminal"
   do script "cd " & quoted form of "$PWD" & "; " & quoted form of "$PYTHON" & " -m src.cli bot"
   do script "cd " & quoted form of "$PWD" & "; " & quoted form of "$PYTHON" & " -m src.cli scheduler"
   activate
 end tell
EOF

echo "Started in Terminal:"
echo "  1. Telegram bot"
echo "  2. Scheduler"
echo
echo "Press Ctrl+C in each Terminal tab/window to stop the program."
read -r -p "Press Enter to close this launcher..."
