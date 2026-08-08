#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"

rm -rf dist build delivery
mkdir -p delivery/app

pyinstaller --noconfirm --clean --onedir \
  --name DiscountParser \
  --hidden-import src.web.app \
  --hidden-import src.web.application \
  --hidden-import src.web.management_pages \
  --hidden-import src.web.system_routes \
  --collect-all uvicorn \
  --collect-all python_calamine \
  src/distribution_entry.py

cp -R dist/DiscountParser/. delivery/app/
cp -R config delivery/app/config
cp -R migrations delivery/app/migrations
cp alembic.ini delivery/app/alembic.ini
cp .env.example delivery/app/.env.example
cp packaging/macos/install.command delivery/install.command
chmod +x delivery/install.command delivery/app/DiscountParser

(
  cd delivery/app
  ./DiscountParser migrate
  # Validate frozen runtime without coupling the build to an unrelated local
  # service that may already use the default control-panel port.
  DP_WEB_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')" ./DiscountParser doctor
)

echo "LOCAL MACOS DELIVERY BUILD: PASSED"
echo "Package directory: delivery/"
