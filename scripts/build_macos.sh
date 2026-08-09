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
  --hidden-import src.web.onboarding_routes \
  --hidden-import src.web.source_registry_routes \
  --hidden-import src.web.source_registry_static_routes \
  --collect-submodules src.modules.source_registry \
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
  qa_dir="$(mktemp -d)"
  trap 'rm -rf "$qa_dir"' EXIT
  export DP_DATABASE_URL="sqlite:///$qa_dir/frozen-smoke.db"
  ./DiscountParser migrate
  # Avoid coupling frozen validation to an unrelated app on the default UI port.
  DP_WEB_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')" ./DiscountParser doctor
)

echo "LOCAL MACOS DELIVERY BUILD: PASSED"
echo "Package directory: delivery/"
