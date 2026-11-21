#!/bin/sh
# Nexus Chat installer: a desktop app you click to run.
#
#   - app        -> ~/.local/bin/nexus-chat.py
#   - shortcut   -> ~/Desktop/nexus-chat.desktop (double-click to
#                   launch) plus an entry in
#                   ~/.local/share/applications for the menu
#
# No autostart: Nexus Chat opens when you click it, like any app.
# It needs Ollama running with a model pulled (see README.md).
# Safe to re-run: files are replaced.
set -e
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"

mkdir -p "$BIN" "$APP_DIR" "$DESKTOP_DIR"

cp "$SRC/nexus-chat.py" "$BIN/nexus-chat.py"
chmod +x "$BIN/nexus-chat.py"
echo "installed $BIN/nexus-chat.py"

cat > "$APP_DIR/nexus-chat.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Nexus Chat
Comment=Local AI chat (Ollama/Qwen3) with memory - nothing leaves this Pi
Exec=python3 $BIN/nexus-chat.py
Icon=utilities-terminal
Terminal=false
Categories=Utility;Chat;
EOF
cp "$APP_DIR/nexus-chat.desktop" "$DESKTOP_DIR/nexus-chat.desktop"
chmod +x "$APP_DIR/nexus-chat.desktop" "$DESKTOP_DIR/nexus-chat.desktop"
echo "installed desktop shortcut $DESKTOP_DIR/nexus-chat.desktop"
echo "done. Click the Nexus Chat icon on the desktop to run it."
