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
chmod +x delivery/install.command delivery/app/DiscountParser packaging/macos/build_dmg.sh

(
  cd delivery/app
  QA_DIR="$(mktemp -d)"
  trap 'rm -rf "$QA_DIR"' EXIT
  QA_PORT="$(python3 - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
  export DP_DATABASE_URL="sqlite:///$QA_DIR/frozen-smoke.db"
  export DP_WEB_PORT="$QA_PORT"
  ./DiscountParser migrate
  ./DiscountParser doctor
)

bash packaging/macos/build_dmg.sh

echo "LOCAL MACOS DELIVERY BUILD: PASSED"
echo "Package directory: delivery/"
echo "DMG: delivery/DiscountParser.dmg"
