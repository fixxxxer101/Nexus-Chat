#!/usr/bin/env bash
# Nexus Gate - FULL setup, start to finish, in one run.
#
#   0. Code          git pull (fast-forward) if this is a checkout,
#                    then the NEW script re-runs itself - so this
#                    one command is also the whole update
#   1. Ollama        (skipped if already installed)
#   2. Ollama API up (starts the service if it is not answering)
#   3. Models        the required models - qwen2.5:3b (chat)
#                    and nomic-embed-text (Knowledge Bases),
#                    skipped if already pulled. Everything
#                    else is optional, from the app's
#                    Download Models window.
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
MODELS="qwen2.5:3b nomic-embed-text"
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
say "Step 0/5: code"
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
say "Step 1/5: Ollama"
if command -v ollama >/dev/null 2>&1; then
  skip "Ollama already installed ($(command -v ollama))"
else
  echo "[setup] installing Ollama (official script)..."
  curl -fsSL https://ollama.com/install.sh | sh \
    || die "the Ollama installer failed - scroll up for its error"
  done_ "Ollama installed"
fi

# ---- 2. API answering ------------------------------------------------
say "Step 2/5: Ollama service"
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
say "Step 3/5: models"
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
say "Step 4/5: Nexus Gate app"
bash "$SRC/install.sh" || die "install.sh failed - scroll up for its error"
# Pillow: smooth scaling for the image viewer. Optional -
# without it the viewer uses Tk's integer scaling, so a
# failure here never stops setup.
if python3 -c "import PIL" >/dev/null 2>&1; then
  skip "Pillow already installed"
elif python3 -m pip install --user --break-system-packages \
       --quiet pillow >/dev/null 2>&1; then
  done_ "Pillow installed"
else
  say "Pillow did not install - the image viewer will use basic scaling"
fi

# ---- 5. Image engine + baseline model ----------------------------------
say "Step 5/5: image engine + baseline model"
DATA_DIR="$HOME/.local/share/nexus-chat"
SD_DIR="$DATA_DIR/sd"
if [ -x "$SD_DIR/sd-cli" ]; then
  skip "image engine already built"
else
  need_pkgs=""
  command -v cmake >/dev/null 2>&1 || need_pkgs="$need_pkgs cmake"
  command -v g++ >/dev/null 2>&1 || need_pkgs="$need_pkgs build-essential"
  command -v git >/dev/null 2>&1 || need_pkgs="$need_pkgs git"
  if [ -n "$need_pkgs" ]; then
    echo "[setup] installing build tools:$need_pkgs"
    sudo apt-get update -qq && sudo apt-get install -y $need_pkgs || die "installing build tools failed"
  fi
  BUILD_DIR="$DATA_DIR/sd-build"
  rm -rf "$BUILD_DIR"
  git clone --depth 1 --branch master-1106-532d2c1 https://github.com/leejet/stable-diffusion.cpp "$BUILD_DIR" || die "cloning stable-diffusion.cpp failed"
  (cd "$BUILD_DIR" && git submodule update --init --recursive) || die "fetching the sd.cpp submodules failed"
  echo "[setup] building sd-cli from source (one time; several minutes on a Pi) ..."
  (cd "$BUILD_DIR" && cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null && (cmake --build build -j"$(nproc)" --target sd-cli || cmake --build build -j"$(nproc)")) || die "building sd-cli failed"
  mkdir -p "$SD_DIR"
  cp "$BUILD_DIR/build/bin/sd-cli" "$SD_DIR/sd-cli"
  printf 'source' > "$SD_DIR/backend.txt"
  rm -rf "$BUILD_DIR"
  done_ "image engine built from source"
fi
IMG_MODELS_DIR="$DATA_DIR/image-models"
BASE="$IMG_MODELS_DIR/DreamShaper8_pruned.safetensors"
mkdir -p "$IMG_MODELS_DIR"
if [ -f "$BASE" ] && [ "$(stat -c%s "$BASE")" -gt 2000000000 ]; then
  skip "baseline image model already downloaded"
else
  echo "[setup] downloading the DreamShaper 8 baseline image model (~2.1 GB) ..."
  curl -L --fail -o "$BASE.part" "https://civitai.com/api/download/models/128713" || die "baseline image model download failed - re-run setup to retry"
  echo "879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd  $BASE.part" | sha256sum -c - >/dev/null || die "baseline image model checksum mismatch - the download was discarded; re-run setup"
  mv "$BASE.part" "$BASE"
  done_ "baseline image model installed (checksum verified)"
fi

# ---- verify -------------------------------------------------------------
say "Verifying"
[ -x "$SD_DIR/sd-cli" ] || die "image engine missing at final check"
[ -f "$BASE" ] || die "baseline image model missing at final check"
api_up || die "API check failed at the end - something is off"
final=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}')
for m in $MODELS; do
  printf '%s\n' "$final" | grep -qx "$m" || die "model $m missing at final check"
done
[ -f "$HOME/Desktop/nexus-chat.desktop" ] || die "desktop icon missing at final check"
printf '\n[setup] ALL DONE. Nexus Gate is ready - click its icon on the desktop.\n'
