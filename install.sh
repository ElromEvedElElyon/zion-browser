#!/bin/bash
# ZionBrowser v2.0 — Global Installer
# Em nome do Senhor Jesus Cristo

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ZION_PY="$SCRIPT_DIR/zion_browser.py"
INSTALL_PATH="/usr/local/bin/zion"

echo "ZionBrowser v2.0 — Installing..."

# Make executable
chmod +x "$ZION_PY"

# Create wrapper script
cat > /tmp/zion_wrapper.sh << WRAPPER
#!/bin/bash
exec python3 "$ZION_PY" "\$@"
WRAPPER

# Install globally
if [ -w /usr/local/bin ]; then
    cp /tmp/zion_wrapper.sh "$INSTALL_PATH"
    chmod +x "$INSTALL_PATH"
else
    sudo cp /tmp/zion_wrapper.sh "$INSTALL_PATH"
    sudo chmod +x "$INSTALL_PATH"
fi

rm /tmp/zion_wrapper.sh

# Create .zion dirs
mkdir -p ~/.zion/{sessions,cache,pipes}

echo ""
echo "  Installed: $INSTALL_PATH"
echo "  Config:    ~/.zion/"
echo ""
echo "  Usage:     zion get https://example.com"
echo "             zion search 'bug bounty'"
echo "             zion i                      # interactive"
echo "             zion cookies import          # import Firefox sessions"
echo ""
echo "  Memory:    ~3-5MB (vs Firefox ~500MB)"
echo "  ZionBrowser ready."
