#!/bin/sh
# Nexus Chat installer: a desktop app you click to run.
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
# No autostart: Nexus Chat opens when you click it, like any app.
# It needs Ollama running with a model pulled (see README.md) -
# setup.sh handles the whole stack.
# Also installs the Ollama Controller (status + Start / Stop /
# Unload panel) with its own shortcut, so the service can be
# halted when its RAM is wanted back.
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
Name=Nexus Chat
Comment=Local AI chat (Ollama/Qwen3) with memory - nothing leaves this Pi
Exec=python3 $BIN/nexus-chat.py
$ICON_LINE
Terminal=false
Categories=Utility;Chat;
EOF
cp "$APP_DIR/nexus-chat.desktop" "$DESKTOP_DIR/nexus-chat.desktop"
chmod +x "$APP_DIR/nexus-chat.desktop" "$DESKTOP_DIR/nexus-chat.desktop"
echo "installed desktop shortcut $DESKTOP_DIR/nexus-chat.desktop"

# ---- Ollama Controller -------------------------------------------
cp "$SRC/ollama-controller.py" "$BIN/ollama-controller.py"
chmod +x "$BIN/ollama-controller.py"
echo "installed $BIN/ollama-controller.py"

CTL_ICON_LINE="Icon=utilities-terminal"
if python3 "$SRC/make_icon.py" power "$ICON_DIR/ollama-controller.png" >/dev/null 2>&1; then
  CTL_ICON_LINE="Icon=$ICON_DIR/ollama-controller.png"
  echo "installed icon $ICON_DIR/ollama-controller.png"
fi

cat > "$APP_DIR/ollama-controller.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Ollama Controller
Comment=Start / stop Ollama and free its RAM
Exec=python3 $BIN/ollama-controller.py
$CTL_ICON_LINE
Terminal=false
Categories=Utility;System;
EOF
cp "$APP_DIR/ollama-controller.desktop" "$DESKTOP_DIR/ollama-controller.desktop"
chmod +x "$APP_DIR/ollama-controller.desktop" "$DESKTOP_DIR/ollama-controller.desktop"
echo "installed desktop shortcut $DESKTOP_DIR/ollama-controller.desktop"

# Mark the launchers trusted so a double-click just opens the app -
# no untrusted-launcher prompt, no "open with" question.
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/nexus-chat.desktop" metadata::trusted true 2>/dev/null || true
  gio set "$APP_DIR/nexus-chat.desktop" metadata::trusted true 2>/dev/null || true
  gio set "$DESKTOP_DIR/ollama-controller.desktop" metadata::trusted true 2>/dev/null || true
  gio set "$APP_DIR/ollama-controller.desktop" metadata::trusted true 2>/dev/null || true
  echo "marked shortcuts trusted (open with no prompt)"
fi
echo "done. Click the Nexus Chat icon on the desktop to run it;"
echo "the Ollama Controller icon starts / stops Ollama."
