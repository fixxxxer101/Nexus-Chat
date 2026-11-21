#!/usr/bin/env python3
"""Ollama Controller - a small control panel for the local Ollama
service, companion to Nexus Chat.

Shows whether the service is running, which model is loaded and
how much RAM it is holding, and gives you the three controls that
matter on a small machine:

  Start   - start the Ollama service (models load on first use)
  Stop    - stop the service entirely: any generation dies and ALL
            RAM Ollama holds is freed
  Unload  - unload the loaded model (frees its RAM) while leaving
            the service up

Same black / green / orange theme and rounded controls as Nexus
Chat. Talks to Ollama at http://localhost:11434 (override with
OLLAMA_CTL_API) and drives the service with systemctl via
passwordless sudo (sudo -n: it never prompts, it just fails
loudly in the status line if sudo is not set up for it).
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request

APP_NAME = "Ollama Controller"
API = os.environ.get("OLLAMA_CTL_API", "http://localhost:11434")
DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share",
                        "ollama-controller")
POLL_MS = 2000

# ---- theme: same family as Nexus Chat ----
BG = "#060806"
PANEL = "#0b100c"
PANEL2 = "#131a13"
PANEL2_HOVER = "#1b261b"
PANEL2_PRESS = "#0d130d"
CARD = "#0e1a10"
CARD_EDGE = "#1e3325"
BORDER = "#1e3325"
GREEN = "#35ff69"
GREEN_DIM = "#3bb96a"
GREEN_FAINT = "#1c5c36"
ORANGE = "#ff8c1a"
ORANGE_HOVER = "#ffa040"
ORANGE_PRESS = "#e07a08"
ORANGE_DIM = "#c77414"
ORANGE_INK = "#170c00"
ERROR = "#ff5a3c"
FONT = "DejaVu Sans"
RADIUS_BTN = 11
RADIUS_BUBBLE = 16

import tkinter as tk
import tkinter.font as tkfont


def _rounded_points(x0, y0, x1, y1, r):
    r = max(0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]


def draw_rounded_rect(canvas, x0, y0, x1, y1, r, **opts):
    return canvas.create_polygon(_rounded_points(x0, y0, x1, y1, r),
                                 smooth=True, splinesteps=16, **opts)


class RoundedButton(tk.Canvas):
    """Canvas-drawn button with rounded corners and hover/press
    states, plus a disabled state the controller needs. Same look
    and API slice as Nexus Chat's."""

    KINDS = {
        "primary": (ORANGE, ORANGE_HOVER, ORANGE_PRESS,
                    ORANGE, ORANGE_INK),
        "ghost": (PANEL2, PANEL2_HOVER, PANEL2_PRESS, BORDER, GREEN),
        "quiet": (PANEL2, PANEL2_HOVER, PANEL2_PRESS,
                  BORDER, GREEN_DIM),
    }

    def __init__(self, master, text="", command=None, kind="ghost",
                 font=None, padx=13, pady=6, radius=RADIUS_BTN, **kw):
        self._font = tkfont.Font(font=font) if font else tkfont.Font(
            family=FONT, size=10, weight="bold")
        self._padx, self._pady = padx, pady
        self._radius = radius
        w = self._font.measure(text) + padx * 2 + 2
        h = self._font.metrics("linespace") + pady * 2 + 2
        bg = kw.pop("bg", None)
        if bg is None:
            try:
                bg = master.cget("bg")
            except Exception:
                bg = BG
        super().__init__(master, width=w, height=h, bg=bg, bd=0,
                         highlightthickness=0, cursor="hand2", **kw)
        self._text = text
        self._command = command
        self._kind = kind
        self._enabled = True
        self._state = "normal"
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_state("hover"))
        self.bind("<Leave>", lambda e: self._set_state("normal"))
        self.bind("<ButtonPress-1>",
                  lambda e: self._set_state("press"))
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self._state = "normal"
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _set_state(self, state):
        if not self._enabled:
            return
        self._state = state
        self._draw()

    def _release(self, e):
        if not self._enabled:
            return
        inside = (0 <= e.x <= self.winfo_width() and
                  0 <= e.y <= self.winfo_height())
        self._set_state("hover" if inside else "normal")
        if inside and self._command:
            self._command()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w = int(self.cget("width"))
        if h <= 1:
            h = int(self.cget("height"))
        fill, hover, press, outline, textcol = self.KINDS[self._kind]
        if not self._enabled:
            fill, outline, textcol = PANEL2, BORDER, GREEN_FAINT
        elif self._state == "hover":
            fill = hover
        elif self._state == "press":
            fill = press
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, self._radius,
                          fill=fill, outline=outline, width=1)
        self.create_text(w / 2.0, h / 2.0, text=self._text,
                         fill=textcol, font=self._font)


class BubbleFrame(tk.Frame):
    """Frame with a rounded-rectangle background on an underlay
    canvas (same component as Nexus Chat's)."""

    def __init__(self, master, fill, outline, radius=RADIUS_BUBBLE,
                 bg=None, **kw):
        super().__init__(master,
                         bg=bg if bg is not None else BG, **kw)
        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._cv = tk.Canvas(self, bg=self.cget("bg"), bd=0,
                             highlightthickness=0)
        self._cv.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        self._cv.delete("all")
        draw_rounded_rect(self._cv, 1, 1, w - 1, h - 1, self._radius,
                          fill=self._fill, outline=self._outline,
                          width=1)


# ---------------------------------------------------------------- probes

def service_state():
    """'active', 'inactive', or whatever systemctl reports."""
    try:
        r = subprocess.run(["systemctl", "is-active", "ollama"],
                           capture_output=True, text=True, timeout=4)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def api_get(path, timeout=3):
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def probe():
    """One status snapshot: service state, loaded models (with RAM),
    installed models."""
    snap = {"service": service_state(), "loaded": None,
            "installed": None}
    try:
        ps = api_get("/api/ps")
        snap["loaded"] = ps.get("models", [])
    except Exception:
        snap["loaded"] = None
    try:
        tags = api_get("/api/tags")
        snap["installed"] = tags.get("models", [])
    except Exception:
        snap["installed"] = None
    return snap


def run_ctl(args):
    """Run a service control command via passwordless sudo.
    Returns (ok, first line of output)."""
    try:
        r = subprocess.run(["sudo", "-n"] + args, capture_output=True,
                           text=True, timeout=20)
        out = (r.stderr or r.stdout or "").strip().splitlines()
        return r.returncode == 0, (out[0] if out else "")
    except Exception as e:
        return False, str(e)


def gb(nbytes):
    return "%.1f GB" % (nbytes / 1e9)


# ---------------------------------------------------------------- app

class Controller:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.snap = None
        self._acting = False
        root.title(APP_NAME)
        root.geometry("500x540")
        root.minsize(440, 480)
        root.configure(bg=BG)
        self._build()
        self.root.after(100, self._drain)
        self._schedule_poll(50)

    def _build(self):
        head = tk.Frame(self.root, bg=PANEL, height=54)
        head.pack(side="top", fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="OLLAMA CONTROLLER", bg=PANEL, fg=GREEN,
                 font=(FONT, 13, "bold")).pack(side="left", padx=14,
                                               pady=14)
        self.pill = tk.Label(head, text="● CHECKING", bg=PANEL,
                             fg=GREEN_DIM, font=(FONT, 10, "bold"))
        self.pill.pack(side="right", padx=14)

        card = BubbleFrame(self.root, fill=CARD, outline=CARD_EDGE,
                           bg=BG)
        card.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(card, text="LOADED MODEL", bg=CARD, fg=GREEN_DIM,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=14,
                                              pady=(10, 0))
        self.loaded_lbl = tk.Label(card, text="—", bg=CARD, fg=GREEN,
                                   font=(FONT, 12, "bold"),
                                   justify="left", anchor="w")
        self.loaded_lbl.pack(anchor="w", padx=14, fill="x")
        self.ram_lbl = tk.Label(card, text="", bg=CARD,
                                fg=GREEN_DIM, font=(FONT, 10),
                                justify="left", anchor="w")
        self.ram_lbl.pack(anchor="w", padx=14, pady=(0, 10), fill="x")

        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=14, pady=8)
        self.start_btn = RoundedButton(row, text="Start",
                                       kind="primary",
                                       font=(FONT, 11, "bold"),
                                       padx=18, pady=8,
                                       command=self._do_start)
        self.start_btn.pack(side="left")
        self.stop_btn = RoundedButton(row, text="Stop", kind="quiet",
                                      font=(FONT, 11, "bold"),
                                      padx=18, pady=8,
                                      command=self._do_stop)
        self.stop_btn.pack(side="left", padx=8)
        self.unload_btn = RoundedButton(row, text="Unload model",
                                        kind="ghost",
                                        font=(FONT, 11, "bold"),
                                        padx=18, pady=8,
                                        command=self._do_unload)
        self.unload_btn.pack(side="left")

        self.msg = tk.Label(self.root, text="", bg=BG, fg=ORANGE_DIM,
                            font=(FONT, 9), justify="left", anchor="w",
                            wraplength=460)
        self.msg.pack(fill="x", padx=14)

        tk.Label(self.root, text="INSTALLED MODELS", bg=BG,
                 fg=GREEN_DIM, font=(FONT, 8, "bold")).pack(
                     anchor="w", padx=14, pady=(10, 2))
        self.models_box = tk.Listbox(
            self.root, bg=PANEL2, fg=GREEN, bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            selectbackground="#17351f", selectforeground=GREEN,
            font=(FONT, 10), activestyle="none", height=7)
        self.models_box.pack(fill="both", expand=True, padx=14,
                             pady=(0, 6))

        tk.Label(self.root,
                 text="Stop frees ALL the RAM Ollama holds. Start "
                      "brings the service back; a model loads on "
                      "first use. Unload frees the model's RAM but "
                      "leaves the service running.",
                 bg=BG, fg=GREEN_DIM, font=(FONT, 9), justify="left",
                 wraplength=460).pack(anchor="w", padx=14,
                                      pady=(0, 12))

    # ---- polling ---------------------------------------------------
    def _schedule_poll(self, delay):
        self.root.after(delay, self._poll)

    def _poll(self):
        def work():
            self.events.put(("snap", probe()))
        threading.Thread(target=work, daemon=True).start()
        self._schedule_poll(POLL_MS)

    def _drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "snap":
                    self._apply(payload)
                elif kind == "acted":
                    ok, err = payload
                    self._acting = False
                    if not ok and err:
                        self.msg.configure(
                            text="Command failed: %s" % err)
                    self._schedule_poll(50)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _apply(self, snap):
        self.snap = snap
        svc = snap["service"]
        loaded = snap["loaded"]
        if svc == "active" and loaded is not None:
            self.pill.configure(text="● RUNNING", fg=GREEN)
        elif svc == "active":
            self.pill.configure(text="● STARTING", fg=ORANGE)
        else:
            self.pill.configure(text="● STOPPED", fg=ERROR)
            loaded = []
        if loaded:
            names = ", ".join(m["name"] for m in loaded)
            total = sum(m.get("size", 0) for m in loaded)
            self.loaded_lbl.configure(text=names)
            self.ram_lbl.configure(
                text="Holding %s of RAM" % gb(total))
        else:
            self.loaded_lbl.configure(text="No model loaded")
            self.ram_lbl.configure(text="RAM is free")
        acting = self._acting
        self.start_btn.set_enabled(svc != "active" and not acting)
        self.stop_btn.set_enabled(svc == "active" and not acting)
        self.unload_btn.set_enabled(bool(loaded) and not acting)
        self.models_box.delete(0, "end")
        for m in (snap["installed"] or []):
            self.models_box.insert(
                "end", "%s   (%s)" % (m["name"], gb(m.get("size", 0))))

    # ---- actions -----------------------------------------------------
    def _act(self, args, verb):
        self._acting = True
        self.msg.configure(text="%s…" % verb)
        self._apply(self.snap or {"service": "unknown",
                                  "loaded": None, "installed": None})

        def work():
            ok, err = run_ctl(args)
            self.events.put(("acted", (ok, err)))
        threading.Thread(target=work, daemon=True).start()

    def _do_start(self):
        self._act(["systemctl", "start", "ollama"], "Starting Ollama")

    def _do_stop(self):
        self._act(["systemctl", "stop", "ollama"], "Stopping Ollama")

    def _do_unload(self):
        loaded = (self.snap or {}).get("loaded") or []
        if not loaded:
            return
        self._acting = True
        self.msg.configure(text="Unloading model…")
        self._apply(self.snap)
        names = [m["name"] for m in loaded]

        def work():
            err = ""
            for name in names:
                try:
                    req = urllib.request.Request(
                        API + "/api/generate",
                        data=json.dumps({"model": name,
                                         "keep_alive": 0}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        r.read()
                except Exception as e:
                    err = str(e)
            self.events.put(("acted", (not err, err)))
        threading.Thread(target=work, daemon=True).start()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    lock_path = os.path.join(DATA_DIR, ".lock")
    lock_file = open(lock_path, "w")
    try:
        import fcntl
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Ollama Controller is already running.")
        return
    root = tk.Tk()
    Controller(root)
    root.mainloop()


if __name__ == "__main__":
    main()
