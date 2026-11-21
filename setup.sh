#!/usr/bin/env bash
# Nexus Chat - FULL setup, start to finish, in one run.
#
#   1. Ollama        (skipped if already installed)
#   2. Ollama API up (starts the service if it is not answering)
#   3. Models        qwen3:4b + qwen3:1.7b (each skipped if pulled)
#   4. The app       via install.sh (desktop icon included)
#
# Idempotent by design: every step checks what already exists and
# skips it, so re-running this is also how you update - git pull,
# then bash setup.sh again, and only the missing pieces happen.
#
# Usage:  bash setup.sh
set -u
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MODELS="qwen3:4b qwen3:1.7b"
API="http://localhost:11434/api/tags"

say()  { printf '\n[setup] %s\n' "$*"; }
skip() { printf '[setup] SKIP - %s\n' "$*"; }
done_() { printf '[setup] done - %s\n' "$*"; }
die()  { printf '\n[setup] STOPPED - %s\n' "$*" >&2; exit 1; }

api_up() { curl -sf "$API" >/dev/null 2>&1; }

# ---- 1. Ollama ------------------------------------------------------
say "Step 1/4: Ollama"
if command -v ollama >/dev/null 2>&1; then
  skip "Ollama already installed ($(command -v ollama))"
else
  echo "[setup] installing Ollama (official script)..."
  curl -fsSL https://ollama.com/install.sh | sh \
    || die "the Ollama installer failed - scroll up for its error"
  done_ "Ollama installed"
fi

# ---- 2. API answering ------------------------------------------------
say "Step 2/4: Ollama service"
if api_up; then
  skip "API already answering at 127.0.0.1:11434"
else
  echo "[setup] API not answering; trying to start the service..."
  sudo -n systemctl start ollama 2>/dev/null || systemctl --user start ollama 2>/dev/null || true
  for i in $(seq 1 30); do
    api_up && break
    sleep 1
  done
  api_up || die "Ollama API still not answering at 127.0.0.1:11434.
       If sudo asked for a password, run:  sudo systemctl start ollama
       then re-run this script - finished steps will be skipped."
  done_ "API is up"
fi

# ---- 3. Models --------------------------------------------------------
say "Step 3/4: models"
have=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}')
for m in $MODELS; do
  if printf '%s\n' "$have" | grep -qx "$m"; then
    skip "model $m already pulled"
  else
    echo "[setup] pulling $m ..."
    ollama pull "$m" || die "pulling $m failed - re-run to resume; finished steps will be skipped"
    done_ "model $m pulled"
  fi
done

# ---- 4. The app --------------------------------------------------------
say "Step 4/4: Nexus Chat app"
bash "$SRC/install.sh" || die "install.sh failed - scroll up for its error"

# ---- verify -------------------------------------------------------------
say "Verifying"
api_up || die "API check failed at the end - something is off"
final=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}')
for m in $MODELS; do
  printf '%s\n' "$final" | grep -qx "$m" || die "model $m missing at final check"
done
[ -f "$HOME/Desktop/nexus-chat.desktop" ] || die "desktop icon missing at final check"
printf '\n[setup] ALL DONE. Nexus Chat is ready - click its icon on the desktop.\n'
