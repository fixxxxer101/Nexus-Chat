#!/bin/sh
# Nexus Gate installer: a desktop app you click to run.
#
#   - app        -> ~/.local/bin/nexus-chat.py
#   - icon       -> ~/.local/share/icons/nexus-chat.png, drawn on
#                   the spot by make_icon.py (pure stdlib)
#   - shortcut   -> ~/Desktop/nexus-chat.desktop (double-click to
#                   launch) plus an entry in
#                   ~/.local/share/applications for the menu, both
#                   marked TRUSTED so the desktop opens them with no
#                   "how do you want to open this?" prompt
#
# No autostart: Nexus Gate opens when you click it, like any app.
# It needs Ollama running with a model pulled (see README.md) -
# setup.sh handles the whole stack. The Ollama controller lives
# INSIDE Nexus Gate (the header's Ollama button) - status, Start /
# Stop / Unload, so the service can be halted when its RAM is
# wanted back.
# Safe to re-run: files are replaced.
set -e
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
ICON_DIR="$HOME/.local/share/icons"

mkdir -p "$BIN" "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR"

cp "$SRC/nexus-chat.py" "$BIN/nexus-chat.py"
chmod +x "$BIN/nexus-chat.py"
echo "installed $BIN/nexus-chat.py"

ICON_LINE="Icon=utilities-terminal"
if python3 "$SRC/make_icon.py" "$ICON_DIR/nexus-chat.png" >/dev/null 2>&1; then
  ICON_LINE="Icon=$ICON_DIR/nexus-chat.png"
  echo "installed icon $ICON_DIR/nexus-chat.png"
fi

cat > "$APP_DIR/nexus-chat.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Nexus Gate
Comment=Local AI chat (Ollama/Qwen3) with memory - nothing leaves this Pi
Exec=python3 $BIN/nexus-chat.py
$ICON_LINE
Terminal=false
Categories=Utility;Chat;
EOF
cp "$APP_DIR/nexus-chat.desktop" "$DESKTOP_DIR/nexus-chat.desktop"
chmod +x "$APP_DIR/nexus-chat.desktop" "$DESKTOP_DIR/nexus-chat.desktop"
echo "installed desktop shortcut $DESKTOP_DIR/nexus-chat.desktop"

# The controller briefly shipped as a standalone app; it now
# lives inside Nexus Gate. Remove the standalone install so there
# is exactly one controller.
rm -f "$BIN/ollama-controller.py" \
      "$APP_DIR/ollama-controller.desktop" \
      "$DESKTOP_DIR/ollama-controller.desktop" \
      "$ICON_DIR/ollama-controller.png"

# Record where this checkout lives so the app's Update button can
# find it later (it runs setup.sh right here, no terminal needed).
DATA_DIR="$HOME/.local/share/nexus-chat"
mkdir -p "$DATA_DIR"
printf '%s' "$SRC" > "$DATA_DIR/repo.txt"
echo "recorded checkout path for the in-app Update button"

# Mark the launchers trusted so a double-click just opens the app -
# no untrusted-launcher prompt, no "open with" question.
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/nexus-chat.desktop" metadata::trusted true 2>/dev/null || true
  gio set "$APP_DIR/nexus-chat.desktop" metadata::trusted true 2>/dev/null || true
  echo "marked shortcut trusted (opens with no prompt)"
fi
echo "done. Click the Nexus Gate icon on the desktop to run it;"
echo "the Ollama button in its header opens the controller."
