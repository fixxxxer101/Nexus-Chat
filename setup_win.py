#!/usr/bin/env python3
"""Nexus Gate setup for Windows - the worker behind setup.bat.

Does everything, skipping whatever is already done:
  0. git pull this checkout (so setup itself is current)
  1. Ollama: found, or the official installer is downloaded and
     launched for Clint to click through - then run setup again
  2. Ollama started if its API is not answering
  3. the required chat model pulled (read from the app file)
  4. the app installed to %LOCALAPPDATA%\\NexusChat with its icon,
     a Desktop shortcut, and the checkout path recorded so the
     app's Update button can find this checkout later
  5. the image engine (sd-cli from stable-diffusion.cpp): the
     GPU is detected and the matching build installed - CUDA
     for NVIDIA, Vulkan for AMD/Intel, CPU as the fallback -
     plus the required baseline image model, checksum-verified

--app-only skips steps 1-3 (what install.bat runs).
Exit codes: 0 done, 2 Ollama installer launched (action needed),
1 failed - the printed lines say why.
"""
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA")
                        or os.path.expanduser("~"), "NexusChat")
DATA_DIR = os.path.join(APP_HOME, "data")
OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
API = "http://localhost:11434"


def say(msg):
    print(msg, flush=True)


def load_models():
    spec = importlib.util.spec_from_file_location(
        "nexuschat", os.path.join(HERE, "nexus-chat.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DEFAULT_MODELS


def self_update(in_app):
    """git pull --ff-only; if THIS file changed and we are not
    running inside the app's Update window, restart setup once
    so the new logic is what runs."""
    if not os.path.isdir(os.path.join(HERE, ".git")):
        return
    me = os.path.abspath(__file__)

    def digest():
        try:
            with open(me, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return ""

    before = digest()
    try:
        r = subprocess.run(["git", "pull", "--ff-only"], cwd=HERE,
                           capture_output=True, text=True, timeout=90)
        for line in (r.stdout or "").splitlines():
            say("git: " + line)
    except Exception as e:
        say("git pull skipped (%s) - continuing with these files."
            % e)
        return
    if (digest() != before and not in_app
            and not os.environ.get("NEXUS_SETUP_UPDATED")):
        say("setup itself updated - restarting it once.")
        os.environ["NEXUS_SETUP_UPDATED"] = "1"
        os.execv(sys.executable, [sys.executable, me] + sys.argv[1:])


def find_ollama():
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles", "")
    for cand in (os.path.join(local, "Programs", "Ollama",
                              "ollama.exe"),
                 os.path.join(prog, "Ollama", "ollama.exe")):
        if cand and os.path.isfile(cand):
            return cand
    return None


def api_up():
    try:
        with urllib.request.urlopen(API + "/api/version",
                                    timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_ollama():
    """Returns (exe, ok). Downloads + launches the installer and
    returns ok=False when Ollama is not installed yet."""
    exe = find_ollama()
    if exe:
        return exe, True
    say("Ollama is not installed. Downloading the official "
        "installer...")
    dest = os.path.join(HERE, "OllamaSetup.exe")
    try:
        urllib.request.urlretrieve(OLLAMA_URL, dest)
    except Exception as e:
        say("Download failed: %s" % e)
        say("Install Ollama from https://ollama.com, then run "
            "setup again.")
        return None, False
    say("Launching the Ollama installer - click through it, "
        "then run setup again.")
    try:
        os.startfile(dest)  # noqa: S606 - the official installer
    except Exception as e:
        say("Could not launch %s: %s" % (dest, e))
    return None, False


def ensure_running(exe):
    if api_up():
        say("Ollama is already running.")
        return True
    say("Starting Ollama...")
    try:
        subprocess.Popen([exe, "serve"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200)
    except Exception as e:
        say("Could not start Ollama: %s" % e)
        return False
    for _ in range(30):
        if api_up():
            say("Ollama is up.")
            return True
        time.sleep(1)
    say("Ollama did not answer after 30 seconds - check its tray "
        "app, then run setup again.")
    return False


def pull_models(exe):
    for model in load_models():
        say("Pulling %s (already-pulled models skip instantly)..."
            % model)
        r = subprocess.run([exe, "pull", model], cwd=HERE)
        if r.returncode != 0:
            say("Pull failed for %s." % model)
            return False
    return True


def make_shortcut():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    lnk = os.path.join(desktop, "Nexus Gate.lnk")
    pyw = os.path.join(os.path.dirname(sys.executable),
                       "pythonw.exe")
    target = pyw if os.path.isfile(pyw) else sys.executable
    app = os.path.join(APP_HOME, "nexus-chat.py")
    icon = os.path.join(APP_HOME, "nexus-chat.ico")
    # PowerShell one-liner through argv (no batch quoting hazards).
    # Paths containing an apostrophe would break the quoting -
    # accepted, Windows profile paths here have none.
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          "$s = $ws.CreateShortcut('%s'); "
          "$s.TargetPath = '%s'; "
          "$s.Arguments = '\"%s\"'; "
          "$s.WorkingDirectory = '%s'; "
          "$s.IconLocation = '%s'; "
          "$s.Save()") % (lnk, target, app, APP_HOME, icon)
    r = subprocess.run(["powershell", "-NoProfile",
                        "-ExecutionPolicy", "Bypass",
                        "-Command", ps],
                       capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        say("Desktop shortcut installed: %s" % lnk)
        # the app was renamed Nexus Chat -> Nexus Gate:
        # take the old-named shortcut away so the desktop
        # does not end up with both
        legacy = os.path.join(desktop, "Nexus Chat.lnk")
        try:
            if os.path.isfile(legacy):
                os.remove(legacy)
                say("Removed the old Nexus Chat shortcut.")
        except OSError:
            pass
        return True
    say("Shortcut creation failed: %s"
        % (r.stderr or r.stdout or "").strip())
    return False


def ensure_pillow():
    """Pillow gives the image viewer smooth scaling.
    Optional: without it the viewer uses Tk's integer
    scaling, so a failure here never stops setup."""
    try:
        import PIL  # noqa: F401
        say("Pillow already installed")
        return
    except ImportError:
        pass
    say("Installing Pillow (image viewer scaling)...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--quiet", "pillow"],
            capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            say("Pillow installed")
        else:
            say("Pillow did not install - the image viewer "
                "will use basic scaling. (pip said: %s)"
                % (r.stderr or "").strip()[-200:])
    except Exception as e:
        say("Pillow did not install (%s) - the image "
            "viewer will use basic scaling." % e)


def install_app():
    ensure_pillow()
    os.makedirs(APP_HOME, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    src = os.path.join(HERE, "nexus-chat.py")
    dst = os.path.join(APP_HOME, "nexus-chat.py")
    shutil.copyfile(src, dst)
    say("installed %s" % dst)
    sys.path.insert(0, HERE)
    import make_icon
    for name in ("nexus-chat.png", "nexus-chat.ico"):
        out = os.path.join(APP_HOME, name)
        data = make_icon.ico_bytes("chat") \
            if name.endswith(".ico") else make_icon.png_bytes("chat")
        with open(out, "wb") as f:
            f.write(data)
        say("installed icon %s" % out)
    with open(os.path.join(DATA_DIR, "repo.txt"), "w") as f:
        f.write(HERE)
    say("recorded checkout path for the in-app Update button")
    make_shortcut()
    return True


SD_RELEASE = "master-1106-532d2c1"
SD_ZIPS = {
    "cuda": ["sd-master-532d2c1-bin-win-cuda12-x64.zip",
             "cudart-sd-bin-win-cu12-x64.zip"],
    "vulkan": ["sd-master-532d2c1-bin-win-vulkan-x64.zip"],
    "cpu": ["sd-master-532d2c1-bin-win-cpu-x64.zip"],
}
IMG_BASELINE_FILE = "DreamShaper8_pruned.safetensors"
IMG_BASELINE_URL = "https://civitai.com/api/download/models/128713"
IMG_BASELINE_SHA256 = \
    "879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd"


def download_file(url, dest, label):
    say("Downloading %s..." % label)
    req = urllib.request.Request(
        url, headers={"User-Agent": "NexusGate-Setup"})
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, -1
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    pct = int(100 * got / total)
                    if pct >= last + 10:
                        last = pct
                        say("  %s: %d%%" % (label, pct))
    return dest


def detect_gpu_backend():
    """Pick the sd-cli build for this machine's GPU: CUDA for
    NVIDIA, Vulkan for AMD/Intel, CPU when nothing is found."""
    names = ""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController).Name "
             "-join ' '"],
            capture_output=True, text=True, timeout=30)
        names = (r.stdout or "").lower()
    except Exception:
        pass
    if "nvidia" in names:
        return "cuda"
    if "amd" in names or "radeon" in names or "intel" in names:
        return "vulkan"
    return "cpu"


def _install_sd_build(backend, dest_dir):
    """Download one sd-cli build's zip(s), find sd-cli.exe
    in the extract and copy its whole folder into dest_dir
    (the builds ship their DLLs beside the exe, and builds
    must never share a folder - their DLLs differ)."""
    tmp = os.path.join(DATA_DIR, "sd-download")
    try:
        os.makedirs(tmp, exist_ok=True)
        for z in SD_ZIPS[backend]:
            zp = os.path.join(tmp, z)
            download_file(
                "https://github.com/leejet/"
                "stable-diffusion.cpp/releases/download/"
                "%s/%s" % (SD_RELEASE, z), zp, z)
            with zipfile.ZipFile(zp) as zf:
                zf.extractall(tmp)
        found = None
        for root, _dirs, files in os.walk(tmp):
            if "sd-cli.exe" in files:
                found = root
                break
        if not found:
            return False
        os.makedirs(dest_dir, exist_ok=True)
        for fn in os.listdir(found):
            srcp = os.path.join(found, fn)
            if os.path.isfile(srcp):
                shutil.copyfile(
                    srcp, os.path.join(dest_dir, fn))
        return os.path.isfile(os.path.join(dest_dir,
                                           "sd-cli.exe"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def install_image_engine():
    sd_dir = os.path.join(DATA_DIR, "sd")
    cli = os.path.join(sd_dir, "sd-cli.exe")
    backend = None
    if os.path.isfile(cli):
        if os.path.isfile(os.path.join(sd_dir, "backend.txt")):
            backend = open(
                os.path.join(sd_dir, "backend.txt")).read() \
                .strip()
        say("Image engine already installed (%s)."
            % (backend or "unknown build"))
    else:
        backend = detect_gpu_backend()
        say("Image engine: installing the %s build of sd-cli "
            "(%s), matched to this machine's GPU..."
            % (backend, SD_RELEASE))
        try:
            if not _install_sd_build(backend, sd_dir):
                say("Image engine: sd-cli.exe was not in the "
                    "download - image generation not "
                    "installed; chat is unaffected.")
                return
            with open(os.path.join(sd_dir, "backend.txt"),
                      "w") as f:
                f.write(backend)
            say("Image engine installed (%s build)."
                % backend)
        except Exception as e:
            say("Image engine install failed: %s - chat is "
                "unaffected; re-run setup to retry." % e)
            return
    # The CPU fallback: a GPU build can crash on a machine's
    # driver (seen live on a Radeon 780M - the Vulkan build
    # died right after loading the model). The app retries
    # on the CPU build automatically when that happens, so
    # it must be here BEFORE it is needed.
    if backend and backend != "cpu":
        fb = os.path.join(sd_dir, "cpu", "sd-cli.exe")
        if os.path.isfile(fb):
            say("Image engine CPU fallback already installed.")
        else:
            say("Image engine: installing the CPU fallback "
                "build alongside it...")
            try:
                if _install_sd_build(
                        "cpu", os.path.join(sd_dir, "cpu")):
                    say("CPU fallback build installed.")
                else:
                    say("CPU fallback: sd-cli.exe was not in "
                        "the download - skipped; the %s "
                        "build still works." % backend)
            except Exception as e:
                say("CPU fallback install failed: %s - "
                    "skipped; the %s build still works."
                    % (e, backend))
    models_dir = os.path.join(DATA_DIR, "image-models")
    dest = os.path.join(models_dir, IMG_BASELINE_FILE)
    if os.path.isfile(dest) and \
            os.path.getsize(dest) > 2_000_000_000:
        say("Baseline image model already downloaded.")
        return
    os.makedirs(models_dir, exist_ok=True)
    part = dest + ".part"
    try:
        download_file(IMG_BASELINE_URL, part,
                      "DreamShaper 8, the baseline image "
                      "model (~2.1 GB)")
        h = hashlib.sha256()
        with open(part, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != IMG_BASELINE_SHA256:
            os.remove(part)
            say("Baseline image model: the checksum did not "
                "match the publisher's hash, so the download "
                "was discarded. Re-run setup to retry.")
            return
        os.replace(part, dest)
        say("Baseline image model installed, checksum "
            "verified.")
    except Exception as e:
        say("Baseline image model download failed: %s - it "
            "can also be downloaded inside the app (Menu -> "
            "Image Models). Re-run setup to retry." % e)


def main():
    app_only = "--app-only" in sys.argv
    in_app = "--no-pause" in sys.argv
    say("Nexus Gate setup (Windows) - checkout: %s" % HERE)
    self_update(in_app)
    if not app_only:
        exe, ok = ensure_ollama()
        if not ok:
            return 2
        if not ensure_running(exe):
            return 1
        if not pull_models(exe):
            return 1
    install_app()
    install_image_engine()
    say("Done. Double-click the Nexus Gate icon on the desktop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
