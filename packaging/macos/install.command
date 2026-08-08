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
rm -rf "$TARGET"/*
cp -R "app/." "$TARGET/"
chmod +x "$TARGET/DiscountParser"

pushd "$TARGET" >/dev/null
echo "Preparing database..."
./DiscountParser migrate
popd >/dev/null

DESKTOP="$HOME/Desktop"
SHORTCUT="$DESKTOP/Discount Parser.command"
mkdir -p "$DESKTOP"
cat > "$SHORTCUT" <<EOF
#!/bin/bash
cd $(printf '%q' "$TARGET")
exec ./DiscountParser
EOF
chmod +x "$SHORTCUT"

echo
echo "Installation completed."
echo "Use 'Discount Parser.command' on the Desktop."
echo "On first launch the browser will open the setup wizard."
echo
read -r -p "Press Enter to close..."
