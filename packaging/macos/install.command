#!/bin/bash
set -e
cd "$(dirname "$0")"

printf '\n========================================\n'
printf 'Discount Parser - Setup\n'
printf '========================================\n\n'

if [ ! -x "app/DiscountParser" ]; then
  echo "[ERROR] Application files are missing."
  read -r -p "Press Enter to close..."
  exit 1
fi

TARGET="$HOME/Applications/DiscountParser"
mkdir -p "$TARGET"

echo "Installing to $TARGET ..."
# Update application files in place. Do not remove the target directory:
# discount_parser.db and .env are user data and must survive upgrades.
cp -R "app/." "$TARGET/"
chmod +x "$TARGET/DiscountParser"

pushd "$TARGET" >/dev/null
echo "Preparing database..."
./DiscountParser migrate
popd >/dev/null

# Build a tiny native-looking .app launcher. It starts the frozen runtime in
# the background so ordinary launches do not open a Terminal window.
LAUNCHER_APP="$HOME/Applications/Discount Parser.app"
rm -rf "$LAUNCHER_APP"
APPLE_SCRIPT="$(mktemp -t discount-parser-launcher).applescript"
TARGET_ESCAPED=$(printf '%q' "$TARGET")
cat > "$APPLE_SCRIPT" <<EOF
on run
    do shell script "cd $TARGET_ESCAPED && nohup ./DiscountParser >/dev/null 2>&1 &"
end run
EOF
osacompile -o "$LAUNCHER_APP" "$APPLE_SCRIPT"
rm -f "$APPLE_SCRIPT"

DESKTOP="$HOME/Desktop"
DESKTOP_APP="$DESKTOP/Discount Parser.app"
mkdir -p "$DESKTOP"
rm -rf "$DESKTOP_APP"
ln -s "$LAUNCHER_APP" "$DESKTOP_APP"

echo
echo "Installation completed."
echo "Use 'Discount Parser.app' on the Desktop."
echo "On first launch the browser will open the setup wizard."
echo
read -r -p "Press Enter to close..."
