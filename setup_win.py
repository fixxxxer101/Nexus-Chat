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


def install_app():
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
    say("Done. Double-click the Nexus Gate icon on the desktop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
