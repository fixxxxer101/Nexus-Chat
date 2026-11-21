#!/usr/bin/env bash
# Nexus Chat - FULL setup, start to finish, in one run.
#
#   0. Code          git pull (fast-forward) if this is a checkout,
#                    then the NEW script re-runs itself - so this
#                    one command is also the whole update
#   1. Ollama        (skipped if already installed)
#   2. Ollama API up (starts the service if it is not answering)
#   3. Models        qwen3:4b + qwen3:1.7b + qwen2.5:3b (each
#                    skipped if pulled; qwen2.5:3b never thinks -
#                    it is the non-thinking option)
#   4. The app       via install.sh (desktop icon included)
#
# Idempotent by design: every step checks what already exists and
# skips it. Running this script is the ONLY step needed to install
# or to update: it pulls the newest code first, then does just the
# pieces that are missing.
#
# Usage:  bash setup.sh
set -u
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MODELS="qwen3:4b qwen3:1.7b qwen2.5:3b"
API="http://localhost:11434/api/tags"

say()  { printf '\n[setup] %s\n' "$*"; }
skip() { printf '[setup] SKIP - %s\n' "$*"; }
done_() { printf '[setup] done - %s\n' "$*"; }
die()  { printf '\n[setup] STOPPED - %s\n' "$*" >&2; exit 1; }

api_up() { curl -sf "$API" >/dev/null 2>&1; }

# ---- 0. Self-update -----------------------------------------------------
# Fast-forward the checkout, then RE-EXEC the new script: a running
# shell must never keep reading a file that was just replaced
# underneath it. Best effort only - offline, a diverged tree, or a
# non-git copy all just continue with the code that's here.
# NEXUS_SETUP_UPDATED stops the re-exec from looping.
say "Step 0/4: code"
if [ "${NEXUS_SETUP_UPDATED:-}" = "1" ]; then
  skip "code already updated this run"
elif [ -d "$SRC/.git" ]; then
  if GIT_TERMINAL_PROMPT=0 git -C "$SRC" pull --ff-only </dev/null >/dev/null 2>&1; then
    done_ "code updated (git pull)"
  else
    echo "[setup] git pull did not complete (offline?) - continuing with the local copy"
  fi
  NEXUS_SETUP_UPDATED=1 exec bash "$SRC/setup.sh" "$@"
else
  skip "not a git checkout - using the code as-is"
fi

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
