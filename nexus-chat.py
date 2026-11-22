#!/usr/bin/env python3
"""Nexus Chat - a local AI chat desktop app. Built for Clint's
Raspberry Pi 5, runs on any Linux PC, and on Windows too.

Talks to Ollama running on the same machine (Qwen3 by default).
Black / green / orange. No accounts, no cloud: chats, memory and
logs all live on this machine (Linux: ~/.local/share/nexus-chat/;
Windows: %LOCALAPPDATA%\\NexusChat\\data).

Features (Clint's spec, 2026-11-21):
  - Thinking traces: when the model thinks (Qwen3), each reply's
    reasoning is a collapsible block (click to expand/collapse),
    saved in the chat log so old reasoning can be re-read. Models
    that never think (e.g. qwen2.5) simply reply - pick per chat
    from the model picker. (There is no thinking on/off toggle:
    Qwen3 in no-think mode still narrated its reasoning inside the
    answer, so the toggle could not be honest. Removed 2026-11-21
    at Clint's direction.)
  - Glass box: the system prompt is visible and editable in the
    app (System button), and the same window previews the EXACT
    context the model receives for the open chat - nothing hidden.
    System prompts can be saved as named presets (save / delete /
    pick in the System window) and switched right in the header
    from the Prompt picker, next to the model picker.
  - An Update button (sidebar) pulls the latest version from the
    git checkout and reinstalls, streaming setup's output into a
    window - no terminal needed. One codebase, both platforms:
    the single-instance lock, data paths, fonts and the Ollama
    controller's start/stop branch per OS (systemd + sudo on
    Linux; the Ollama app + taskkill on Windows).
  - Chat logs: every conversation auto-saved, listed in a sidebar.
  - Long-term memory, both modes: manual (view / edit / add) and
    automatic (the model proposes entries; nothing is kept until
    Clint approves it).
  - The rolling chat itself is memory too, with selective context
    compression: when the context window fills, the model folds
    older turns into a "key topics" note - weighted by what is
    talked about MOST, decisions and facts kept, one-off tangents
    pruned. The ORIGIN of the chat (its first exchange) is pinned
    and never compressed away: it is what led to where we are.
    Compression only changes what the model sees; the saved log
    always keeps every word.

Pure Python 3 + Tkinter + urllib. No extra packages.
Backend URL override for testing: NEXUS_OLLAMA=http://host:port
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

APP_NAME = "Nexus Chat"
IS_WINDOWS = os.name == "nt"
OLLAMA = os.environ.get("NEXUS_OLLAMA", "http://localhost:11434")
if IS_WINDOWS:
    _app_home = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "NexusChat")
    DATA_DIR = os.path.join(_app_home, "data")
    LOG_PATH = os.path.join(DATA_DIR, "nexus-chat.log")
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), ".local",
                            "share", "nexus-chat")
    LOG_PATH = os.path.join(os.path.expanduser("~"), ".local",
                            "state", "nexus-chat.log")
CHATS_DIR = os.path.join(DATA_DIR, "chats")
MEMORY_PATH = os.path.join(DATA_DIR, "memory.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
DEFAULT_MODELS = ["qwen3:4b", "qwen3:1.7b", "qwen2.5:3b"]
NUM_CTX = 4096
# context budget (rough tokens, chars/4): compress when the assembled
# context passes COMPRESS_AT; always keep the last KEEP_RAW messages
# (after the origin pair) word-for-word.
COMPRESS_AT = 2700
KEEP_RAW = 6
PROPOSE_EVERY = 8          # user turns between memory-proposal passes

# ---- theme: black, green lettering, orange highlight -------------
# Modern pass (2026-11-21): same palette family, softer surfaces,
# rounded everything. All widgets draw from these constants - the
# theme is built into the app, not scattered inline.
BG = "#060806"           # window + chat background (soft black)
PANEL = "#0b100c"        # header / sidebar surface
PANEL2 = "#131a13"       # control fill (ghost buttons, fields)
PANEL2_HOVER = "#1b261b"
PANEL2_PRESS = "#0d130d"
BUBBLE_BOT = "#0e1a10"   # assistant message bubble
BUBBLE_BOT_EDGE = "#1e3325"
BUBBLE_USER = "#1d1307"  # user message bubble (dark amber)
BUBBLE_USER_EDGE = "#3d290f"
BORDER = "#1e3325"       # soft outline for fields and bubbles
GREEN = "#35ff69"
GREEN_DIM = "#3bb96a"
GREEN_FAINT = "#1c5c36"
ORANGE = "#ff8c1a"
ORANGE_HOVER = "#ffa040"
ORANGE_PRESS = "#e07a08"
ORANGE_DIM = "#c77414"
ORANGE_INK = "#170c00"   # text on orange fills
USER_TEXT = "#ffd9a3"    # user message text (warm, in-family)
THINK_GREEN = "#5fbf8a"
ERROR = "#ff5a3c"
if IS_WINDOWS:
    FONT = "Segoe UI"
    MONO = "Consolas"
else:
    FONT = "DejaVu Sans"
    MONO = "DejaVu Sans Mono"
RADIUS_BUBBLE = 22
RADIUS_FIELD = 20
RADIUS_CARD = 18      # header / sidebar / bottom bar cards
RADIUS_PANEL = 14     # text and list panels inside windows

SYSTEM_PROMPT = (
    "You are the assistant inside Nexus Chat, a private local chat "
    "app running entirely on the user's own Raspberry Pi. Be direct, "
    "accurate and concise unless asked for depth. Everything here is "
    "offline and private."
)
# The system prompt is NOT a black box: it lives in the settings
# (key "system_prompt", defaulting to the text above) and is
# viewable + editable in the app via the System button, which also
# previews the exact context sent to the model. Glass box.

COMPRESS_PROMPT = """You maintain the compressed memory of a long conversation.

Below are the current KEY TOPICS notes (may be empty) and the next chunk of the conversation. Produce updated notes.

Rules:
- Record what this conversation is MAINLY about: recurring topics first, weighted by how much they are discussed.
- Keep decisions, conclusions, and concrete facts (names, numbers, choices made).
- Drop one-off tangents, small talk, and anything mentioned once and never returned to.
- Merge new material into existing topics instead of repeating them; if a topic has stopped being discussed, shrink it.
- Compact bullet lines starting with "- ", plain text, no preamble, no headings. At most about 350 words.

CURRENT NOTES:
{notes}

NEXT CHUNK OF CONVERSATION:
{chunk}
"""

EXTRACT_PROMPT = """From the conversation below, list durable facts about the USER worth remembering in future conversations: preferences, people, projects, setups, decisions.

Rules:
- One fact per line, a plain statement, nothing else (no bullets, no numbering).
- Durable only: skip one-off questions, small talk, and anything temporary.
- Do not repeat anything already in the EXISTING MEMORY list.
- If there is nothing new and durable, reply with exactly: NONE

EXISTING MEMORY:
{memory}

CONVERSATION:
{chunk}
"""


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def est_tokens(text):
    return (len(text) + 3) // 4


def supports_thinking(model):
    m = (model or "").lower()
    return m.startswith("qwen3") or m.startswith("deepseek-r1")


# ---------------------------------------------------------------- Ollama

def api_get(path, timeout=4):
    with urllib.request.urlopen(OLLAMA + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def api_chat_once(model, messages, think_off=True):
    """One non-streaming chat call; returns the reply text."""
    payload = {"model": model, "messages": messages, "stream": False,
               "options": {"num_ctx": NUM_CTX}}
    if supports_thinking(model) and think_off:
        payload["think"] = False
    req = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message") or {}).get("content", "").strip()


class ThinkSplitter:
    """Splits <think>...</think> spans out of a content stream.

    Some models/templates leak their reasoning into the answer text
    as literal think tags instead of the API's thinking field. Those
    spans belong in the collapsible thinking block, not the answer.
    """
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.in_think = False
        self.buf = ""

    def _safe_len(self, s, tag):
        # how much of s cannot be the beginning of tag
        for k in range(min(len(s), len(tag) - 1), 0, -1):
            if tag.startswith(s[-k:]):
                return len(s) - k
        return len(s)

    def feed(self, text):
        self.buf += text
        events = []
        while True:
            tag = self.CLOSE if self.in_think else self.OPEN
            idx = self.buf.find(tag)
            kind = "thinking" if self.in_think else "content"
            if idx == -1:
                n = self._safe_len(self.buf, tag)
                if n:
                    events.append((kind, self.buf[:n]))
                    self.buf = self.buf[n:]
                break
            if idx:
                events.append((kind, self.buf[:idx]))
            self.buf = self.buf[idx + len(tag):]
            self.in_think = not self.in_think
        return events

    def flush(self):
        if not self.buf:
            return []
        kind = "thinking" if self.in_think else "content"
        out = [(kind, self.buf)]
        self.buf = ""
        return out


class Streamer:
    """Runs one streaming /api/chat call on a thread; events go to a
    queue as ("thinking", text), ("content", text), ("done", None),
    ("error", message)."""

    def __init__(self, model, messages, events):
        self.model = model
        self.messages = messages
        self.events = events
        self.stopped = threading.Event()
        self._resp = None

    def stop(self):
        self.stopped.set()
        try:
            if self._resp is not None:
                self._resp.close()
        except Exception:
            pass

    def run(self):
        payload = {"model": self.model, "messages": self.messages,
                   "stream": True, "options": {"num_ctx": NUM_CTX}}
        if supports_thinking(self.model):
            # Thinking models think, and the trace is shown in its
            # collapsible block. There is no off switch (see the
            # module docstring for why); models that never think
            # are never sent the key at all.
            payload["think"] = True
        req = urllib.request.Request(
            OLLAMA + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        splitter = ThinkSplitter()
        try:
            # Local inference is slow: model load + prompt eval can
            # sit silent for minutes, and a buffered thinking phase
            # sends nothing until it completes. A chat stream gets a
            # generous 30-minute read timeout - the Stop button is
            # the user's way out of a genuinely stuck reply.
            self._resp = urllib.request.urlopen(req, timeout=1800)
            for raw in self._resp:
                if self.stopped.is_set():
                    break
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw.decode("utf-8"))
                except ValueError:
                    continue
                msg = data.get("message") or {}
                if msg.get("thinking"):
                    self.events.put(("thinking", msg["thinking"]))
                if msg.get("content"):
                    for kind, text in splitter.feed(msg["content"]):
                        self.events.put((kind, text))
                if data.get("error"):
                    self.events.put(("error", str(data["error"])))
            for kind, text in splitter.flush():
                self.events.put((kind, text))
            self.events.put(("done", None))
        except Exception as e:  # connection refused, closed on stop, ...
            if self.stopped.is_set():
                self.events.put(("done", None))
            else:
                self.events.put(("error", str(e)))
        finally:
            # ALWAYS hang up deterministically. If the socket lingers
            # open, Ollama keeps generating a reply nobody is reading
            # and pins the Pi's CPU doing it (seen live 2026-11-21:
            # a timed-out thinking reply ran the runner at 363% CPU
            # until the service was restarted).
            try:
                if self._resp is not None:
                    self._resp.close()
            except Exception:
                pass
            self._resp = None


# ---------------------------------------------------------------- storage

def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


class Store:
    def __init__(self):
        os.makedirs(CHATS_DIR, exist_ok=True)
        self.memory = _load_json(MEMORY_PATH,
                                 {"entries": [], "pending": []})
        self.settings = _load_json(SETTINGS_PATH,
                                   {"model": "qwen3:4b", "think": False})
        self.chats = {}
        for name in os.listdir(CHATS_DIR):
            if name.endswith(".json"):
                chat = _load_json(os.path.join(CHATS_DIR, name), None)
                if chat and "id" in chat:
                    self.chats[chat["id"]] = chat

    # -- chats
    def new_chat(self):
        cid = time.strftime("%Y%m%d-%H%M%S") + "-%d" % (time.time() % 1000)
        chat = {"id": cid, "title": "New chat",
                "created": time.time(), "updated": time.time(),
                "messages": [], "origin": None, "topics": "",
                "folded": 0, "proposed_upto": 0}
        self.chats[cid] = chat
        self.save_chat(chat)
        return chat

    def save_chat(self, chat):
        chat["updated"] = time.time()
        _save_json(os.path.join(CHATS_DIR, chat["id"] + ".json"), chat)

    def delete_chat(self, cid):
        self.chats.pop(cid, None)
        try:
            os.remove(os.path.join(CHATS_DIR, cid + ".json"))
        except OSError:
            pass

    def sorted_chats(self):
        return sorted(self.chats.values(),
                      key=lambda c: c["updated"], reverse=True)

    # -- memory / settings
    def save_memory(self):
        _save_json(MEMORY_PATH, self.memory)

    def save_settings(self):
        _save_json(SETTINGS_PATH, self.settings)


# ---------------------------------------------------------------- context

def build_context(store, chat, model):
    """Assemble the message list the model sees for the next reply:
    system (+ long-term memory) + pinned origin + compressed key
    topics + the raw tail. The full log on disk is never altered."""
    system = (store.settings.get("system_prompt") or "").strip() \
        or SYSTEM_PROMPT
    entries = store.memory.get("entries") or []
    if entries:
        system += "\n\nLong-term memory about the user:\n" + \
            "\n".join("- " + e for e in entries)
    msgs = [{"role": "system", "content": system}]
    if chat.get("origin"):
        o = chat["origin"]
        msgs.append({"role": "user", "content": o["user"]})
        msgs.append({"role": "assistant", "content": o["assistant"]})
    if chat.get("topics"):
        msgs.append({"role": "system", "content":
                     "Compressed memory of the earlier conversation "
                     "(key topics, weighted by how much they were "
                     "discussed):\n" + chat["topics"]})
    start = (2 if chat.get("origin") else 0) + chat.get("folded", 0)
    for m in chat["messages"][start:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    return msgs


def context_tokens(store, chat):
    return sum(est_tokens(m["content"]) + 4
               for m in build_context(store, chat, None))


def _format_chunk(messages):
    lines = []
    for m in messages:
        who = "User" if m["role"] == "user" else "Assistant"
        lines.append("%s: %s" % (who, m["content"]))
    return "\n".join(lines)


def maybe_compress(store, chat, model):
    """Fold older turns into the key-topics note when the context is
    over budget. Returns True if a compression pass ran. The origin
    pair is never folded; the last KEEP_RAW turns stay raw."""
    if context_tokens(store, chat) <= COMPRESS_AT:
        return False
    base = 2 if chat.get("origin") else 0
    tail = chat["messages"][base + chat.get("folded", 0):]
    if len(tail) <= KEEP_RAW:
        return False
    chunk = tail[:len(tail) - KEEP_RAW]
    prompt = COMPRESS_PROMPT.format(notes=chat.get("topics") or "(empty)",
                                    chunk=_format_chunk(chunk))
    notes = api_chat_once(model, [{"role": "user", "content": prompt}])
    if notes:
        chat["topics"] = notes
        chat["folded"] = chat.get("folded", 0) + len(chunk)
        store.save_chat(chat)
        log("compressed chat %s: folded %d turns" % (chat["id"], len(chunk)))
        return True
    return False


def propose_memories(store, chat, model):
    """Ask the model for durable facts from the turns not yet mined;
    new ones land in the PENDING list - never straight into memory."""
    base = chat.get("proposed_upto", 0)
    fresh = chat["messages"][base:]
    if not fresh:
        return 0
    prompt = EXTRACT_PROMPT.format(
        memory="\n".join("- " + e for e in store.memory["entries"]) or "(empty)",
        chunk=_format_chunk(fresh))
    out = api_chat_once(model, [{"role": "user", "content": prompt}])
    chat["proposed_upto"] = len(chat["messages"])
    store.save_chat(chat)
    if not out or out.upper() == "NONE":
        return 0
    known = {e.strip().lower() for e in store.memory["entries"]}
    known |= {p.strip().lower() for p in store.memory["pending"]}
    added = 0
    for line in out.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if line and line.lower() not in known:
            store.memory["pending"].append(line)
            known.add(line.lower())
            added += 1
    if added:
        store.save_memory()
        log("proposed %d memories from chat %s" % (added, chat["id"]))
    return added


# ------------------------------------------------- Ollama controller

def ollama_exe():
    """Path of the Windows Ollama executable, or None."""
    if not IS_WINDOWS:
        return None
    cands = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        cands.append(os.path.join(local, "Programs", "Ollama",
                                  "ollama.exe"))
    prog = os.environ.get("ProgramFiles", "")
    if prog:
        cands.append(os.path.join(prog, "Ollama", "ollama.exe"))
    for cand in cands:
        if os.path.isfile(cand):
            return cand
    return shutil.which("ollama")


def service_state():
    """'active', 'inactive', or whatever the platform reports.
    Linux: the systemd unit. Windows: Ollama is a user app, not a
    service, so 'active' means its API answers."""
    if IS_WINDOWS:
        try:
            api_get("/api/version")
            return "active"
        except Exception:
            return "inactive"
    try:
        r = subprocess.run(["systemctl", "is-active", "ollama"],
                           capture_output=True, text=True, timeout=4)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def ctl_probe():
    """One controller snapshot: service state, loaded models (with
    the RAM they hold), installed models."""
    snap = {"service": service_state(), "loaded": None,
            "installed": None}
    try:
        snap["loaded"] = api_get("/api/ps").get("models", [])
    except Exception:
        snap["loaded"] = None
    try:
        snap["installed"] = api_get("/api/tags").get("models", [])
    except Exception:
        snap["installed"] = None
    return snap


def run_ctl(args):
    """Run a service control command via passwordless sudo
    (sudo -n: never prompts; failure shows in the panel)."""
    try:
        r = subprocess.run(["sudo", "-n"] + args, capture_output=True,
                           text=True, timeout=20)
        out = (r.stderr or r.stdout or "").strip().splitlines()
        return r.returncode == 0, (out[0] if out else "")
    except Exception as e:
        return False, str(e)


def ctl_service(action):
    """Start or stop Ollama, per platform. (ok, error message).
    Linux drives the systemd unit; Windows starts ollama.exe
    detached, and stops it with taskkill - which frees ALL the
    RAM it holds, the whole point of the Stop button."""
    if IS_WINDOWS:
        if action == "start":
            exe = ollama_exe()
            if not exe:
                return False, "ollama.exe not found - is Ollama " \
                              "installed?"
            try:
                subprocess.Popen(
                    [exe, "serve"], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x00000008 | 0x00000200)
                return True, ""
            except Exception as e:
                return False, str(e)
        try:
            r = subprocess.run(["taskkill", "/IM", "ollama.exe",
                                "/F"], capture_output=True,
                               text=True, timeout=20)
            if r.returncode == 0:
                return True, ""
            out = (r.stderr or r.stdout or "").strip().splitlines()
            return False, (out[0] if out else "taskkill failed")
        except Exception as e:
            return False, str(e)
    return run_ctl(["systemctl", action, "ollama"])


def gb(nbytes):
    return "%.1f GB" % (nbytes / 1e9)


# ---------------------------------------------------------------- GUI

import tkinter as tk
import tkinter.font as tkfont


def _rounded_points(x0, y0, x1, y1, r):
    """Polygon points tracing a rounded rectangle; draw with
    smooth=True for corners with no sharp edges anywhere."""
    r = max(0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]


def draw_rounded_rect(canvas, x0, y0, x1, y1, r, **opts):
    return canvas.create_polygon(_rounded_points(x0, y0, x1, y1, r),
                                 smooth=True, splinesteps=16, **opts)


class RoundedButton(tk.Canvas):
    """A button with genuinely rounded corners, drawn on a canvas -
    stock Tk buttons are rectangles and cannot be rounded. Speaks
    the slice of the tk.Button API this app uses: configure(text=,
    fg=), pack/place, and a command callback. Hover and press states
    are drawn, not just coloured."""

    KINDS = {
        # kind: (fill, hover, press, outline, text colour)
        "primary": (ORANGE, ORANGE_HOVER, ORANGE_PRESS,
                    ORANGE, ORANGE_INK),
        "ghost": (PANEL2, PANEL2_HOVER, PANEL2_PRESS, BORDER, GREEN),
        "quiet": (PANEL2, PANEL2_HOVER, PANEL2_PRESS,
                  BORDER, GREEN_DIM),
    }

    def __init__(self, master, text="", command=None, kind="ghost",
                 font=None, padx=14, pady=6, radius=None, **kw):
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
        self._fg = None
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
        # radius=None means a true pill: ends fully rounded at
        # half the button's height. Modern chat apps are pills and
        # big soft corners everywhere - a slight radius reads as a
        # rectangle with a defect, not as a style.
        r = self._radius if self._radius is not None \
            else (h - 2) / 2.0
        draw_rounded_rect(self, 1, 1, w - 1, h - 1, r,
                          fill=fill, outline=outline, width=1)
        self.create_text(w / 2.0, h / 2.0, text=self._text,
                         fill=self._fg or textcol, font=self._font)

    def configure(self, **kw):
        text = kw.pop("text", None)
        fg = kw.pop("fg", None)
        if text is not None and text != self._text:
            self._text = text
            super().configure(
                width=self._font.measure(text) + self._padx * 2 + 2,
                height=self._font.metrics("linespace") +
                self._pady * 2 + 2)
        if fg is not None:
            self._fg = fg
        if kw:
            super().configure(**kw)
        if text is not None or fg is not None:
            self._draw()

    config = configure


class BubbleFrame(tk.Frame):
    """A frame whose background is a rounded rectangle, drawn on an
    underlay canvas that sits behind everything packed into it.
    Children pack in exactly like a plain frame (same pack order,
    same geometry behaviour); the canvas is placed, never packed,
    and redraws itself whenever the frame changes size."""

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


class App:
    def __init__(self, root):
        import tkinter as tk
        self.tk = tk
        self.root = root
        self.store = Store()
        self.events = queue.Queue()
        self.streamer = None
        self.busy = False
        self.current = None            # chat dict being shown
        self.blocks = []               # rendered message frames
        self.block_objs = []           # matching per-message block dicts
        self._wrap_labels = []         # labels needing wraplength updates
        self._cur = None               # streaming block state
        self.model = tk.StringVar(value=self.store.settings.get(
            "model", "qwen3:4b"))
        self._at_bottom = True
        self._ctl = None               # Ollama controller panel state
        self._upd = None               # Update window state

        root.title(APP_NAME)
        root.geometry("1040x700")
        root.minsize(780, 540)
        root.configure(bg=BG)
        if IS_WINDOWS:
            ico = os.path.join(os.path.dirname(DATA_DIR),
                               "nexus-chat.ico")
            if os.path.isfile(ico):
                try:
                    root.iconbitmap(ico)
                except Exception:
                    pass
        self._build_layout()
        chats = self.store.sorted_chats()
        self.open_chat(chats[0] if chats else self.store.new_chat())
        self.refresh_sidebar()
        self.root.after(60, self._drain)
        self.root.after(300, self._check_ollama)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- layout ------------------------------------------------------
    def _build_layout(self):
        tk = self.tk
        head = BubbleFrame(self.root, fill=PANEL, outline=BORDER,
                           radius=RADIUS_CARD, bg=BG, height=56)
        head.pack(side="top", fill="x", padx=10, pady=(10, 2))
        head.pack_propagate(False)
        tk.Label(head, text="NEXUS CHAT", bg=PANEL, fg=GREEN,
                 font=(FONT, 14, "bold")).pack(side="left", padx=16)
        self.status = tk.Label(head, text="", bg=PANEL, fg=GREEN_DIM,
                               font=(FONT, 9))
        self.status.pack(side="right", padx=14)
        RoundedButton(head, text="Memory", kind="ghost", bg=PANEL,
                      font=(FONT, 10, "bold"),
                      command=self.open_memory).pack(side="right",
                                                     pady=11)
        RoundedButton(head, text="System", kind="ghost", bg=PANEL,
                      font=(FONT, 10, "bold"),
                      command=self.open_system).pack(side="right",
                                                     padx=8, pady=11)
        RoundedButton(head, text="Ollama", kind="ghost", bg=PANEL,
                      font=(FONT, 10, "bold"),
                      command=self.open_controller).pack(side="right",
                                                         pady=11)
        self._model_names = [self.model.get()]
        self.model_btn = RoundedButton(head, text=self.model.get(),
                                       kind="ghost", font=(FONT, 10),
                                       bg=PANEL,
                                       command=self._model_popup)
        self.model_btn.pack(side="right", pady=11)
        tk.Label(head, text="Model", bg=PANEL, fg=GREEN_DIM,
                 font=(FONT, 9)).pack(side="right", padx=(0, 6))
        self.prompt_btn = RoundedButton(head, text="", kind="ghost",
                                        font=(FONT, 10), bg=PANEL,
                                        command=self._prompt_popup)
        self.prompt_btn.pack(side="right", pady=11)
        tk.Label(head, text="Prompt", bg=PANEL, fg=GREEN_DIM,
                 font=(FONT, 9)).pack(side="right", padx=(0, 6))
        self._refresh_prompt_btn()

        body = tk.Frame(self.root, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        side = BubbleFrame(body, fill=PANEL, outline=BORDER,
                           radius=RADIUS_CARD, bg=BG, width=224)
        side.pack(side="left", fill="y", padx=(10, 0), pady=10)
        side.pack_propagate(False)
        RoundedButton(side, text="+  New Chat", kind="primary",
                      bg=PANEL, font=(FONT, 11, "bold"), pady=8,
                      command=self.new_chat).pack(fill="x", padx=12,
                                                  pady=12)
        self.chat_list = tk.Listbox(
            side, bg=PANEL, fg=GREEN, selectbackground="#17351f",
            selectforeground=GREEN, bd=0, highlightthickness=0,
            font=(FONT, 10), activestyle="none")
        self.chat_list.pack(fill="both", expand=True, padx=8)
        self.chat_list.bind("<<ListboxSelect>>", self._sidebar_pick)
        RoundedButton(side, text="Delete chat", kind="quiet",
                      bg=PANEL, font=(FONT, 9),
                      command=self.delete_current
                      ).pack(fill="x", padx=12, pady=(12, 6))
        RoundedButton(side, text="Update", kind="ghost",
                      bg=PANEL, font=(FONT, 9),
                      command=self.open_update
                      ).pack(fill="x", padx=12, pady=(0, 12))

        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(main, bg=BG, bd=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(main, orient="vertical",
                                      command=self.canvas.yview,
                                      bg=GREEN_DIM, troughcolor=PANEL2,
                                      bd=0, width=12,
                                      activebackground=GREEN)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.flow = tk.Frame(self.canvas, bg=BG)
        self._flow_win = self.canvas.create_window((0, 0),
                                                   window=self.flow,
                                                   anchor="nw")
        self.flow.bind("<Configure>", self._on_flow_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

        bar = BubbleFrame(self.root, fill=PANEL, outline=BORDER,
                          radius=RADIUS_CARD, bg=BG)
        bar.pack(side="bottom", fill="x", padx=10, pady=(2, 10))
        field = BubbleFrame(bar, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_FIELD, bg=PANEL)
        field.pack(side="left", fill="both", expand=True,
                   padx=(12, 4), pady=12)
        self.input = tk.Text(field, height=3, bg=PANEL2, fg=GREEN,
                             insertbackground=ORANGE, bd=0,
                             highlightthickness=0,
                             font=(FONT, 11), wrap="word")
        self.input.pack(fill="both", expand=True, padx=12, pady=8)
        self.input.bind("<Return>", self._enter)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.input.focus_set()
        self.send_btn = RoundedButton(bar, text="Send", kind="primary",
                                      bg=PANEL, font=(FONT, 12, "bold"),
                                      padx=22, pady=10,
                                      command=self._send_or_stop)
        self.send_btn.pack(side="right", padx=12, pady=12)

    # ---- model picker --------------------------------------------------
    def _model_popup(self):
        tk = self.tk
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=GREEN,
                       activebackground=GREEN_FAINT,
                       activeforeground=GREEN, bd=0,
                       font=(FONT, 10))
        for name in (self._model_names or DEFAULT_MODELS):
            menu.add_command(
                label=name,
                command=lambda n=name: self._pick_model(n))
        x = self.model_btn.winfo_rootx()
        y = (self.model_btn.winfo_rooty() +
             self.model_btn.winfo_height())
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _pick_model(self, name):
        self.model.set(name)
        self.model_btn.configure(text=name)

    # ---- prompt presets ------------------------------------------
    # Presets are named system prompts, managed in the System
    # window and switchable right here in the header, exactly like
    # models. Picking one copies its text into the working
    # system_prompt setting, so build_context needs no preset
    # logic of its own - glass all the way down.

    def _presets(self):
        return self.store.settings.get("prompt_presets") or []

    def _prompt_label(self):
        text = (self.store.settings.get("system_prompt") or "").strip()
        if not text:
            return "Default"
        name = self.store.settings.get("prompt_name") or ""
        for p in self._presets():
            if p.get("name") == name and \
                    (p.get("text") or "").strip() == text:
                return name
        return "Custom"

    def _refresh_prompt_btn(self):
        self.prompt_btn.configure(text=self._prompt_label())

    def _prompt_popup(self):
        tk = self.tk
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=GREEN,
                       activebackground=GREEN_FAINT,
                       activeforeground=GREEN, bd=0,
                       font=(FONT, 10))
        menu.add_command(label="Default (built-in)",
                         command=lambda: self._pick_prompt(None))
        for p in self._presets():
            menu.add_command(
                label=p.get("name", "?"),
                command=lambda n=p.get("name"): self._pick_prompt(n))
        menu.add_separator()
        menu.add_command(label="Manage prompts…",
                         command=self.open_system)
        x = self.prompt_btn.winfo_rootx()
        y = (self.prompt_btn.winfo_rooty() +
             self.prompt_btn.winfo_height())
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _pick_prompt(self, name):
        if name is None:
            self.store.settings["system_prompt"] = ""
            self.store.settings["prompt_name"] = ""
        else:
            for p in self._presets():
                if p.get("name") == name:
                    self.store.settings["system_prompt"] = \
                        p.get("text", "")
                    self.store.settings["prompt_name"] = name
                    break
            else:
                return
        self.store.save_settings()
        self._refresh_prompt_btn()

    def _save_preset(self, name, text):
        name = (name or "").strip()
        if not name:
            return False
        presets = [p for p in self._presets()
                   if p.get("name") != name]
        presets.append({"name": name, "text": text})
        self.store.settings["prompt_presets"] = presets
        self.store.settings["system_prompt"] = text
        self.store.settings["prompt_name"] = name
        self.store.save_settings()
        self._refresh_prompt_btn()
        return True

    def _delete_preset(self, name):
        presets = [p for p in self._presets()
                   if p.get("name") != name]
        if len(presets) == len(self._presets()):
            return False
        self.store.settings["prompt_presets"] = presets
        if self.store.settings.get("prompt_name") == name:
            self.store.settings["prompt_name"] = ""
        self.store.save_settings()
        self._refresh_prompt_btn()
        return True

    # ---- system prompt (glass box) -------------------------------
    def open_system(self):
        """See and edit the system prompt, and preview the EXACT
        context the model receives for the open chat. Nothing about
        what the model is told stays hidden."""
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title("System Prompt")
        win.geometry("700x780")
        win.configure(bg=BG)
        tk.Label(win, text="SYSTEM PROMPT", bg=BG, fg=GREEN,
                 font=(FONT, 12, "bold")).pack(anchor="w", padx=12,
                                               pady=(12, 2))
        tk.Label(win, text="This is the instruction the app puts at "
                           "the top of every conversation. Edit it, "
                           "Save, and it applies from the next message "
                           "on. An empty box means the built-in "
                           "default (shown by Reset).",
                 bg=BG, fg=GREEN_DIM, font=(FONT, 9), justify="left",
                 wraplength=640).pack(anchor="w", padx=12)
        ewrap = BubbleFrame(win, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        ewrap.pack(fill="x", padx=12, pady=8)
        editor = tk.Text(ewrap, height=7, bg=PANEL2, fg=GREEN,
                         insertbackground=ORANGE, bd=0,
                         highlightthickness=0, font=(FONT, 10),
                         wrap="word")
        editor.pack(fill="both", expand=True, padx=9, pady=7)
        editor.insert("1.0", self.store.settings.get(
            "system_prompt") or SYSTEM_PROMPT)

        saved = tk.Label(win, text="", bg=BG, fg=ORANGE_DIM,
                         font=(FONT, 9))
        btnrow = tk.Frame(win, bg=BG)
        btnrow.pack(fill="x", padx=12)

        def save():
            text = editor.get("1.0", "end").strip()
            self.store.settings["system_prompt"] = text
            match = ""
            for p in self._presets():
                if text and (p.get("text") or "").strip() == text:
                    match = p.get("name", "")
                    break
            self.store.settings["prompt_name"] = match
            self.store.save_settings()
            self._refresh_prompt_btn()
            saved.configure(text="Saved. The preview below already "
                                 "uses it.")
            refresh_preview()

        def reset():
            editor.delete("1.0", "end")
            editor.insert("1.0", SYSTEM_PROMPT)

        RoundedButton(btnrow, text="Save", kind="primary",
                      font=(FONT, 10, "bold"),
                      command=save).pack(side="left")
        RoundedButton(btnrow, text="Reset to default", kind="quiet",
                      font=(FONT, 10),
                      command=reset).pack(side="left", padx=8)
        saved.pack(anchor="w", padx=12, pady=(4, 0))

        tk.Label(win, text="PROMPT PRESETS", bg=BG, fg=GREEN,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=12,
                                               pady=(14, 2))
        tk.Label(win, text="Click a preset to use it — it loads "
                           "above and applies from the next message, "
                           "and the header's Prompt picker switches "
                           "the same list. Save the editor's text "
                           "under a name to keep it; saving an "
                           "existing name updates that preset.",
                 bg=BG, fg=GREEN_DIM, font=(FONT, 9), justify="left",
                 wraplength=640).pack(anchor="w", padx=12)
        prow = tk.Frame(win, bg=BG)
        prow.pack(fill="x", padx=12, pady=(6, 0))
        pwrap = BubbleFrame(prow, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        pwrap.pack(side="left", fill="both", expand=True)
        plist = tk.Listbox(pwrap, height=4, bg=PANEL2, fg=GREEN,
                           bd=0, highlightthickness=0,
                           selectbackground="#17351f",
                           selectforeground=GREEN, font=(FONT, 10),
                           activestyle="none")
        plist.pack(fill="both", expand=True, padx=8, pady=6)
        pcol = tk.Frame(prow, bg=BG)
        pcol.pack(side="left", padx=(8, 0), fill="y")
        nwrap = BubbleFrame(pcol, fill=PANEL2, outline=BORDER,
                            radius=11, bg=BG)
        nwrap.pack(anchor="w")
        name_ent = tk.Entry(nwrap, bg=PANEL2, fg=GREEN,
                            insertbackground=ORANGE, bd=0,
                            highlightthickness=0,
                            font=(FONT, 10), width=16)
        name_ent.pack(padx=8, pady=5)

        def refresh_plist():
            plist.delete(0, "end")
            for p in self._presets():
                plist.insert("end", p.get("name", "?"))

        def on_pick(_e=None):
            sel = plist.curselection()
            if not sel:
                return
            name = plist.get(sel[0])
            for p in self._presets():
                if p.get("name") == name:
                    editor.delete("1.0", "end")
                    editor.insert("1.0", p.get("text", ""))
                    name_ent.delete(0, "end")
                    name_ent.insert(0, name)
                    self._pick_prompt(name)
                    saved.configure(text="Preset '%s' is now "
                                         "active." % name)
                    refresh_preview()
                    break

        plist.bind("<<ListboxSelect>>", on_pick)

        def save_preset():
            if self._save_preset(name_ent.get(),
                                 editor.get("1.0", "end").strip()):
                refresh_plist()
                saved.configure(text="Preset saved and active.")
                refresh_preview()
            else:
                saved.configure(text="Give the preset a name first.")

        def delete_preset():
            sel = plist.curselection()
            name = (plist.get(sel[0]) if sel
                    else name_ent.get().strip())
            if name and self._delete_preset(name):
                refresh_plist()
                saved.configure(text="Preset '%s' deleted. The "
                                     "working prompt text above is "
                                     "unchanged." % name)
                refresh_preview()

        RoundedButton(pcol, text="Save as preset", kind="primary",
                      font=(FONT, 9, "bold"),
                      command=save_preset).pack(anchor="w",
                                                pady=(6, 4))
        RoundedButton(pcol, text="Delete preset", kind="quiet",
                      font=(FONT, 9),
                      command=delete_preset).pack(anchor="w")
        refresh_plist()

        tk.Label(win, text="WHAT THE MODEL ACTUALLY RECEIVES — "
                           "this chat, right now", bg=BG, fg=GREEN,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=12,
                                                pady=(14, 2))
        tk.Label(win, text="Your prompt, plus the parts the app "
                           "appends: long-term memory inside the "
                           "system message, the pinned origin, the "
                           "compressed-topics note when a long chat "
                           "has one, then the messages themselves.",
                 bg=BG, fg=GREEN_DIM, font=(FONT, 9), justify="left",
                 wraplength=640).pack(anchor="w", padx=12)
        vwrap = BubbleFrame(win, fill=PANEL, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        vwrap.pack(fill="both", expand=True, padx=12, pady=8)
        preview = tk.Text(vwrap, bg=PANEL, fg=GREEN_DIM, bd=0,
                          highlightthickness=0,
                          font=(FONT, 9), wrap="word",
                          state="disabled")
        preview.pack(fill="both", expand=True, padx=9, pady=7)

        def refresh_preview():
            chat = self.current
            if chat is None:
                body = "(no chat open)"
            else:
                msgs = build_context(self.store, chat,
                                     self.model.get())
                lines = ["Chat: %s   ·   %d messages   ·   ~%d "
                         "tokens" % (chat.get("title", "?"),
                                     len(msgs),
                                     sum(est_tokens(m["content"]) + 4
                                         for m in msgs)), ""]
                for m in msgs:
                    lines.append("[%s]" % m["role"].upper())
                    lines.append(m["content"])
                    lines.append("")
                body = "\n".join(lines)
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", body)
            preview.configure(state="disabled")

        RoundedButton(win, text="Refresh preview", kind="ghost",
                      font=(FONT, 9),
                      command=refresh_preview).pack(anchor="w",
                                                    padx=12,
                                                    pady=(0, 10))
        refresh_preview()

    # ---- scrolling ---------------------------------------------------
    def _on_scroll(self, first, last):
        self.scrollbar.set(first, last)
        self._at_bottom = float(last) >= 0.999

    def _on_flow_configure(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self._at_bottom:
            self.canvas.yview_moveto(1.0)

    def _on_canvas_configure(self, e):
        self.canvas.itemconfigure(self._flow_win, width=e.width)
        wrap = max(200, e.width - 130)
        for lbl in self._wrap_labels:
            lbl.configure(wraplength=wrap)

    def _on_wheel(self, e):
        if e.num == 4:
            self.canvas.yview_scroll(-3, "units")
        elif e.num == 5:
            self.canvas.yview_scroll(3, "units")
        else:
            self.canvas.yview_scroll(int(-e.delta / 40) or
                                     (-3 if e.delta > 0 else 3), "units")

    # ---- chat list / switching ---------------------------------------
    def refresh_sidebar(self):
        self.chat_list.delete(0, "end")
        for c in self.store.sorted_chats():
            self.chat_list.insert("end", c["title"][:30])
        ids = [c["id"] for c in self.store.sorted_chats()]
        if self.current and self.current["id"] in ids:
            self.chat_list.selection_set(ids.index(self.current["id"]))

    def _sidebar_pick(self, _e):
        sel = self.chat_list.curselection()
        if not sel:
            return
        chat = self.store.sorted_chats()[sel[0]]
        if not self.current or chat["id"] != self.current["id"]:
            self.open_chat(chat)

    def new_chat(self):
        if self.busy:
            return
        self._propose_async(self.current)
        self.open_chat(self.store.new_chat())
        self.refresh_sidebar()

    def delete_current(self):
        if self.busy or not self.current:
            return
        self.store.delete_chat(self.current["id"])
        chats = self.store.sorted_chats()
        self.open_chat(chats[0] if chats else self.store.new_chat())
        self.refresh_sidebar()

    def open_chat(self, chat):
        self.current = chat
        for b in self.blocks:
            b.destroy()
        self.blocks = []
        self.block_objs = []
        self._wrap_labels = []
        for m in chat["messages"]:
            self._render_message(m["role"], m.get("content", ""),
                                 m.get("thinking", ""))
        self._at_bottom = True
        self.canvas.yview_moveto(1.0)

    # ---- rendering ---------------------------------------------------
    def _render_message(self, role, content, thinking=""):
        tk = self.tk
        user = role == "user"
        fill = BUBBLE_USER if user else BUBBLE_BOT
        frame = BubbleFrame(self.flow, fill=fill,
                            outline=(BUBBLE_USER_EDGE if user
                                     else BUBBLE_BOT_EDGE),
                            bg=BG)
        frame.pack(anchor="e" if user else "w", padx=12, pady=5)
        self.blocks.append(frame)
        tk.Label(frame, text="YOU" if user else "NEXUS", bg=fill,
                 fg=ORANGE if user else GREEN,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=12,
                                              pady=(8, 0))
        block = {"frame": frame, "thinking_lbl": None,
                 "thinking_head": None, "open": False}
        self.block_objs.append(block)
        if thinking:
            self._add_thinking(block, thinking)
        lbl = tk.Label(frame, text=content, bg=fill,
                       fg=USER_TEXT if user else GREEN,
                       font=(FONT, 11), justify="left", anchor="w",
                       wraplength=600)
        lbl.pack(fill="x", anchor="w", padx=12, pady=(2, 9))
        self._wrap_labels.append(lbl)
        block["content_lbl"] = lbl
        return block

    def _add_thinking(self, block, text):
        tk = self.tk
        head = tk.Label(block["frame"], text="▸ Thinking",
                        bg=BUBBLE_BOT, fg=ORANGE_DIM,
                        font=(FONT, 9, "italic"), cursor="hand2")
        if block.get("content_lbl") is not None:
            # streaming: the answer label already exists - the
            # thinking header belongs ABOVE it, not below
            head.pack(anchor="w", padx=12, before=block["content_lbl"])
        else:
            head.pack(anchor="w", padx=12)
        lbl = tk.Label(block["frame"], text=text, bg=BUBBLE_BOT,
                       fg=THINK_GREEN, font=(FONT, 10, "italic"),
                       justify="left", anchor="w", wraplength=600)

        def toggle(_e=None, b=block):
            b["open"] = not b["open"]
            if b["open"]:
                b["thinking_lbl"].pack(fill="x", anchor="w", padx=12,
                                       before=b["content_lbl"])
                b["thinking_head"].configure(text="▾ Thinking")
            else:
                b["thinking_lbl"].pack_forget()
                b["thinking_head"].configure(text="▸ Thinking")

        head.bind("<Button-1>", toggle)
        block["thinking_head"] = head
        block["thinking_lbl"] = lbl
        block["toggle"] = toggle
        self._wrap_labels.append(lbl)

    # ---- sending / streaming -----------------------------------------
    def _enter(self, _e):
        self._send_or_stop()
        return "break"

    def _send_or_stop(self):
        if self.busy:
            if self.streamer:
                self.streamer.stop()
            return
        text = self.input.get("1.0", "end").strip()
        if not text or not self.current:
            return
        self.input.delete("1.0", "end")
        chat = self.current
        chat["messages"].append({"role": "user", "content": text,
                                 "thinking": ""})
        if chat["title"] == "New chat":
            chat["title"] = text[:40]
        self.store.save_chat(chat)
        self.refresh_sidebar()
        self._render_message("user", text)
        self._at_bottom = True
        self.canvas.yview_moveto(1.0)

        model = self.model.get()
        self.store.settings["model"] = model
        self.store.save_settings()
        block = self._render_message("assistant", "", "")
        self._cur = {"block": block, "content": "", "thinking": ""}
        ctx = build_context(self.store, chat, model)
        self.streamer = Streamer(model, ctx, self.events)
        self.busy = True
        self.send_btn.configure(text="Stop")
        self.status.configure(text="Generating…", fg=ORANGE)
        threading.Thread(target=self.streamer.run, daemon=True).start()

    def _drain(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind in ("thinking", "content") and self._cur:
                    self._cur[kind] += text
                    block = self._cur["block"]
                    if kind == "thinking":
                        if block["thinking_lbl"] is None:
                            self._add_thinking(block, "")
                        block["thinking_lbl"].configure(
                            text=self._cur["thinking"])
                        self.status.configure(text="Thinking…", fg=ORANGE)
                    else:
                        block["content_lbl"].configure(
                            text=self._cur["content"])
                        self.status.configure(text="Generating…", fg=ORANGE)
                    if self._at_bottom:
                        self.canvas.yview_moveto(1.0)
                elif kind == "error":
                    self._finish_stream(error=text)
                elif kind == "done":
                    self._finish_stream()
                elif kind == "status":
                    self.status.configure(text=text, fg=GREEN_DIM)
                elif kind == "models":
                    self._on_models(text)
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    def _finish_stream(self, error=None):
        if not self.busy:
            return
        self.busy = False
        self.send_btn.configure(text="Send")
        self.status.configure(text="", fg=GREEN_DIM)
        cur, self._cur = self._cur, None
        self.streamer = None
        chat = self.current
        if chat is None or cur is None:
            return
        content = cur["content"]
        if error and not content:
            content = ("⚠ Could not reach the model: %s\n"
                       "Is Ollama running? Start it with:  ollama serve"
                       % error)
            log("stream error: %s" % error)
            # Show the failure in the chat, not just in the saved
            # log - an empty reply box teaches the user nothing.
            try:
                cur["block"]["content_lbl"].configure(text=content)
            except Exception:
                pass
        msg = {"role": "assistant", "content": content,
               "thinking": cur["thinking"]}
        chat["messages"].append(msg)
        if chat.get("origin") is None and len(chat["messages"]) >= 2:
            chat["origin"] = {"user": chat["messages"][0]["content"],
                              "assistant": chat["messages"][1]["content"]}
        self.store.save_chat(chat)
        self.refresh_sidebar()
        self._background_passes(chat)

    def _background_passes(self, chat):
        """Compression + memory proposals, off the GUI thread."""
        model = self.model.get()

        def work():
            try:
                if maybe_compress(self.store, chat, model):
                    self.events.put(("status", "Memory compressed"))
            except Exception as e:
                log("compress failed: %s" % e)
            user_turns = sum(1 for m in chat["messages"]
                             if m["role"] == "user")
            if user_turns and user_turns % PROPOSE_EVERY == 0:
                self._propose_async(chat)

        threading.Thread(target=work, daemon=True).start()

    def _propose_async(self, chat):
        if not chat or not chat.get("messages"):
            return
        model = self.model.get()

        def work():
            try:
                n = propose_memories(self.store, chat, model)
                if n:
                    self.events.put(("status",
                                     "%d memory proposal(s) waiting "
                                     "in Memory" % n))
            except Exception as e:
                log("propose failed: %s" % e)

        threading.Thread(target=work, daemon=True).start()

    # ---- ollama status -------------------------------------------------
    def _check_ollama(self):
        def work():
            try:
                data = api_get("/api/tags", timeout=3)
                names = [m["name"] for m in data.get("models", [])]
                self.events.put(("models", names))
            except Exception:
                self.events.put(("models", None))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(20000, self._check_ollama)

    def _on_models(self, names):
        if names is None:
            self.status.configure(text="Ollama: NOT RUNNING", fg=ERROR)
            return
        if not self.busy:
            self.status.configure(text="Ollama ready", fg=GREEN_DIM)
        self._model_names = names or DEFAULT_MODELS
        if names and self.model.get() not in names:
            self.model.set(names[0])
        self.model_btn.configure(text=self.model.get())

    def _on_close(self):
        self.store.save_settings()
        self.root.destroy()

    # ---- in-app update -------------------------------------------------
    # The sidebar's Update button: runs the platform setup inside
    # the git checkout (setup.sh / setup.bat), which pulls the
    # latest code and reinstalls - the terminal flow, minus the
    # terminal. Output streams into the window as it happens, and
    # Relaunch starts the new version once setup succeeds.

    def open_update(self):
        tk = self.tk
        if self._upd is not None:
            try:
                self._upd["win"].deiconify()
                self._upd["win"].lift()
                return
            except Exception:
                self._upd = None
        win = tk.Toplevel(self.root)
        win.title("Update Nexus Chat")
        win.geometry("580x470")
        win.configure(bg=BG)
        upd = {"win": win, "queue": queue.Queue(), "running": False,
               "ok": False, "drain_id": None}
        self._upd = upd
        tk.Label(win, text="UPDATE NEXUS CHAT", bg=BG, fg=GREEN,
                 font=(FONT, 12, "bold")).pack(anchor="w", padx=12,
                                               pady=(12, 2))
        repo = find_repo()
        if repo:
            info = ("Pulls the latest version from your git "
                    "checkout and reinstalls - models included, "
                    "exactly what setup does in a terminal.\n"
                    "Checkout: %s" % repo)
        else:
            info = ("This install does not know where its git "
                    "checkout is, so it cannot update itself. Run "
                    "setup once from a terminal inside the checkout "
                    "- it records the path, and this button works "
                    "from then on.")
        tk.Label(win, text=info, bg=BG, fg=GREEN_DIM,
                 font=(FONT, 9), justify="left",
                 wraplength=540).pack(anchor="w", padx=12)
        lwrap = BubbleFrame(win, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        lwrap.pack(fill="both", expand=True, padx=12, pady=8)
        log_view = tk.Text(lwrap, bg=PANEL2, fg=GREEN_DIM, bd=0,
                           highlightthickness=0, font=(MONO, 9),
                           wrap="word", state="disabled")
        log_view.pack(fill="both", expand=True, padx=9, pady=7)
        status = tk.Label(win, text="", bg=BG, fg=ORANGE_DIM,
                          font=(FONT, 9))
        btnrow = tk.Frame(win, bg=BG)
        btnrow.pack(fill="x", padx=12, pady=(0, 4))

        def log_line(text):
            log_view.configure(state="normal")
            log_view.insert("end", text + "\n")
            log_view.see("end")
            log_view.configure(state="disabled")

        def start():
            if upd["running"] or not repo:
                return
            upd["running"] = True
            upd["ok"] = False
            run_btn.set_enabled(False)
            relaunch_btn.set_enabled(False)
            status.configure(text="Updating…")

            def work():
                if IS_WINDOWS:
                    cmd = ["cmd", "/c", "setup.bat", "--no-pause"]
                else:
                    cmd = ["bash", "setup.sh"]
                try:
                    proc = subprocess.Popen(
                        cmd, cwd=repo, stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True,
                        bufsize=1)
                    for line in proc.stdout:
                        upd["queue"].put(("line", line.rstrip()))
                    rc = proc.wait()
                except Exception as e:
                    upd["queue"].put(("line", "ERROR: %s" % e))
                    rc = -1
                upd["queue"].put(("done", rc))

            threading.Thread(target=work, daemon=True).start()
            drain()

        def drain():
            if self._upd is not upd:
                return
            try:
                while True:
                    kind, payload = upd["queue"].get_nowait()
                    if kind == "line":
                        log_line(payload)
                    else:
                        upd["running"] = False
                        upd["ok"] = payload == 0
                        run_btn.set_enabled(True)
                        if upd["ok"]:
                            status.configure(
                                text="Update installed. Relaunch "
                                     "to use the new version.")
                            relaunch_btn.set_enabled(
                                installed_app_cmd() is not None)
                        else:
                            status.configure(
                                text="Update failed (exit %s) - "
                                     "the log above shows why."
                                     % payload)
            except queue.Empty:
                pass
            upd["drain_id"] = self.root.after(90, drain)

        def relaunch():
            cmd = installed_app_cmd()
            if not cmd:
                status.configure(text="Cannot find the installed "
                                      "app to relaunch.")
                return
            code = ("import subprocess, sys, time; "
                    "time.sleep(1.2); "
                    "subprocess.Popen(sys.argv[1:], "
                    "close_fds=True)")
            kw = {"stdin": subprocess.DEVNULL,
                  "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL}
            if IS_WINDOWS:
                kw["creationflags"] = 0x00000008  # DETACHED_PROCESS
            else:
                kw["start_new_session"] = True
            try:
                subprocess.Popen([sys.executable, "-c", code] + cmd,
                                 **kw)
            except Exception as e:
                status.configure(text="Relaunch failed: %s" % e)
                return
            self._upd = None
            self._on_close()

        run_btn = RoundedButton(btnrow, text="Check for updates",
                                kind="primary",
                                font=(FONT, 10, "bold"),
                                command=start)
        run_btn.pack(side="left")
        run_btn.set_enabled(repo is not None)
        relaunch_btn = RoundedButton(btnrow, text="Relaunch",
                                     kind="ghost", font=(FONT, 10),
                                     command=relaunch)
        relaunch_btn.pack(side="left", padx=8)
        relaunch_btn.set_enabled(False)
        RoundedButton(btnrow, text="Close", kind="quiet",
                      font=(FONT, 10),
                      command=lambda: self._upd_close(upd)).pack(
                          side="left")
        status.pack(anchor="w", padx=12, pady=(0, 10))
        win.protocol("WM_DELETE_WINDOW",
                     lambda: self._upd_close(upd))

    def _upd_close(self, upd):
        if self._upd is not upd:
            return
        self._upd = None
        if upd.get("drain_id"):
            try:
                self.root.after_cancel(upd["drain_id"])
            except Exception:
                pass
        try:
            upd["win"].destroy()
        except Exception:
            pass

    # ---- memory window -------------------------------------------------
    # ---- Ollama controller panel --------------------------------
    # A window inside Nexus Chat (the header's Ollama button): live
    # service status, the loaded model and the RAM it holds, and
    # Start / Stop / Unload controls. Stop frees ALL the RAM Ollama
    # holds; Unload frees just the model's.

    def open_controller(self):
        tk = self.tk
        if self._ctl is not None:
            try:
                self._ctl["win"].deiconify()
                self._ctl["win"].lift()
                return
            except Exception:
                self._ctl = None
        win = tk.Toplevel(self.root)
        win.title("Ollama Controller")
        win.geometry("500x540")
        win.minsize(440, 480)
        win.configure(bg=BG)
        ctl = {"win": win, "queue": queue.Queue(), "snap": None,
               "acting": False, "poll_id": None, "drain_id": None}
        self._ctl = ctl

        head = BubbleFrame(win, fill=PANEL, outline=BORDER,
                           radius=RADIUS_CARD, bg=BG, height=56)
        head.pack(side="top", fill="x", padx=10, pady=(10, 0))
        head.pack_propagate(False)
        tk.Label(head, text="OLLAMA CONTROLLER", bg=PANEL, fg=GREEN,
                 font=(FONT, 13, "bold")).pack(side="left", padx=16,
                                               pady=14)
        ctl["pill"] = tk.Label(head, text="● CHECKING", bg=PANEL,
                               fg=GREEN_DIM, font=(FONT, 10, "bold"))
        ctl["pill"].pack(side="right", padx=14)

        card = BubbleFrame(win, fill=BUBBLE_BOT,
                           outline=BUBBLE_BOT_EDGE, bg=BG)
        card.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(card, text="LOADED MODEL", bg=BUBBLE_BOT,
                 fg=GREEN_DIM, font=(FONT, 8, "bold")).pack(
                     anchor="w", padx=14, pady=(10, 0))
        ctl["loaded_lbl"] = tk.Label(card, text="—", bg=BUBBLE_BOT,
                                     fg=GREEN, font=(FONT, 12, "bold"),
                                     justify="left", anchor="w")
        ctl["loaded_lbl"].pack(anchor="w", padx=14, fill="x")
        ctl["ram_lbl"] = tk.Label(card, text="", bg=BUBBLE_BOT,
                                  fg=GREEN_DIM, font=(FONT, 10),
                                  justify="left", anchor="w")
        ctl["ram_lbl"].pack(anchor="w", padx=14, pady=(0, 10),
                            fill="x")

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=14, pady=8)
        ctl["start_btn"] = RoundedButton(
            row, text="Start", kind="primary", font=(FONT, 11, "bold"),
            padx=18, pady=8,
            command=lambda: self._ctl_act(ctl, "start",
                                          "Starting Ollama"))
        ctl["start_btn"].pack(side="left")
        ctl["stop_btn"] = RoundedButton(
            row, text="Stop", kind="quiet", font=(FONT, 11, "bold"),
            padx=18, pady=8,
            command=lambda: self._ctl_act(ctl, "stop",
                                          "Stopping Ollama"))
        ctl["stop_btn"].pack(side="left", padx=8)
        ctl["unload_btn"] = RoundedButton(
            row, text="Unload model", kind="ghost",
            font=(FONT, 11, "bold"), padx=18, pady=8,
            command=lambda: self._ctl_unload(ctl))
        ctl["unload_btn"].pack(side="left")

        ctl["msg"] = tk.Label(win, text="", bg=BG, fg=ORANGE_DIM,
                              font=(FONT, 9), justify="left",
                              anchor="w", wraplength=460)
        ctl["msg"].pack(fill="x", padx=14)

        tk.Label(win, text="INSTALLED MODELS", bg=BG, fg=GREEN_DIM,
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=14,
                                              pady=(10, 2))
        mwrap = BubbleFrame(win, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        mwrap.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        ctl["models_box"] = tk.Listbox(
            mwrap, bg=PANEL2, fg=GREEN, bd=0, highlightthickness=0,
            selectbackground="#17351f",
            selectforeground=GREEN, font=(FONT, 10),
            activestyle="none", height=7)
        ctl["models_box"].pack(fill="both", expand=True, padx=8,
                               pady=6)
        tk.Label(win, text="Stop frees ALL the RAM Ollama holds. "
                           "Start brings the service back; a model "
                           "loads on first use. Unload frees the "
                           "model's RAM but leaves the service "
                           "running.",
                 bg=BG, fg=GREEN_DIM, font=(FONT, 9), justify="left",
                 wraplength=460).pack(anchor="w", padx=14,
                                      pady=(0, 12))

        win.protocol("WM_DELETE_WINDOW",
                     lambda: self._ctl_close(ctl))
        self._ctl_poll(ctl, 50)
        self._ctl_drain(ctl)

    def _ctl_close(self, ctl):
        if self._ctl is not ctl:
            return
        self._ctl = None
        for key in ("poll_id", "drain_id"):
            if ctl.get(key):
                try:
                    self.root.after_cancel(ctl[key])
                except Exception:
                    pass
        try:
            ctl["win"].destroy()
        except Exception:
            pass

    def _ctl_poll(self, ctl, delay):
        if self._ctl is not ctl:
            return

        def tick():
            if self._ctl is not ctl:
                return

            def work():
                ctl["queue"].put(("snap", ctl_probe()))
            threading.Thread(target=work, daemon=True).start()
            self._ctl_poll(ctl, 2000)
        ctl["poll_id"] = self.root.after(delay, tick)

    def _ctl_drain(self, ctl):
        if self._ctl is not ctl:
            return
        try:
            while True:
                kind, payload = ctl["queue"].get_nowait()
                if kind == "snap":
                    self._ctl_apply(ctl, payload)
                elif kind == "acted":
                    ok, err = payload
                    ctl["acting"] = False
                    if not ok and err:
                        ctl["msg"].configure(
                            text="Command failed: %s" % err)
                    self._ctl_poll(ctl, 50)
        except queue.Empty:
            pass
        ctl["drain_id"] = self.root.after(
            100, lambda: self._ctl_drain(ctl))

    def _ctl_apply(self, ctl, snap):
        if self._ctl is not ctl:
            return
        ctl["snap"] = snap
        svc = snap["service"]
        loaded = snap["loaded"]
        if svc == "active" and loaded is not None:
            ctl["pill"].configure(text="● RUNNING", fg=GREEN)
        elif svc == "active":
            ctl["pill"].configure(text="● STARTING", fg=ORANGE)
        else:
            ctl["pill"].configure(text="● STOPPED", fg=ERROR)
            loaded = []
        if loaded:
            ctl["loaded_lbl"].configure(
                text=", ".join(m["name"] for m in loaded))
            ctl["ram_lbl"].configure(
                text="Holding %s of RAM" %
                gb(sum(m.get("size", 0) for m in loaded)))
        else:
            ctl["loaded_lbl"].configure(text="No model loaded")
            ctl["ram_lbl"].configure(text="RAM is free")
        acting = ctl["acting"]
        ctl["start_btn"].set_enabled(svc != "active" and not acting)
        ctl["stop_btn"].set_enabled(svc == "active" and not acting)
        ctl["unload_btn"].set_enabled(bool(loaded) and not acting)
        ctl["models_box"].delete(0, "end")
        for m in (snap["installed"] or []):
            ctl["models_box"].insert(
                "end", "%s   (%s)" % (m["name"], gb(m.get("size", 0))))

    def _ctl_act(self, ctl, action, verb):
        if self._ctl is not ctl or ctl["acting"]:
            return
        ctl["acting"] = True
        ctl["msg"].configure(text="%s…" % verb)
        if ctl["snap"]:
            self._ctl_apply(ctl, ctl["snap"])

        def work():
            ok, err = ctl_service(action)
            ctl["queue"].put(("acted", (ok, err)))
        threading.Thread(target=work, daemon=True).start()

    def _ctl_unload(self, ctl):
        if self._ctl is not ctl or ctl["acting"]:
            return
        loaded = (ctl["snap"] or {}).get("loaded") or []
        if not loaded:
            return
        ctl["acting"] = True
        ctl["msg"].configure(text="Unloading model…")
        self._ctl_apply(ctl, ctl["snap"])
        names = [m["name"] for m in loaded]

        def work():
            err = ""
            for name in names:
                try:
                    req = urllib.request.Request(
                        OLLAMA + "/api/generate",
                        data=json.dumps({"model": name,
                                         "keep_alive": 0}).encode(),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        r.read()
                except Exception as e:
                    err = str(e)
            ctl["queue"].put(("acted", (not err, err)))
        threading.Thread(target=work, daemon=True).start()

    def open_memory(self):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title("Nexus Chat — Memory")
        win.geometry("560x520")
        win.configure(bg=BG)
        store = self.store

        tk.Label(win, text="LONG-TERM MEMORY", bg=BG, fg=GREEN,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        tk.Label(win, text="Fed to the model at the start of every chat.",
                 bg=BG, fg=GREEN_DIM, font=(FONT, 9)).pack(anchor="w", padx=10)
        ewrap = BubbleFrame(win, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        ewrap.pack(fill="x", padx=10, pady=4)
        entries = tk.Listbox(ewrap, bg=PANEL2, fg=GREEN,
                             selectbackground=ORANGE,
                             selectforeground="#000000", bd=0,
                             highlightthickness=0,
                             font=(FONT, 10), height=8)
        entries.pack(fill="both", expand=True, padx=8, pady=6)

        addrow = tk.Frame(win, bg=BG)
        addrow.pack(fill="x", padx=10)
        nwrap = BubbleFrame(addrow, fill=PANEL2, outline=BORDER,
                            radius=11, bg=BG)
        nwrap.pack(side="left", fill="x", expand=True)
        new_entry = tk.Entry(nwrap, bg=PANEL2, fg=GREEN,
                             insertbackground=ORANGE, bd=0,
                             highlightthickness=0,
                             font=(FONT, 10))
        new_entry.pack(fill="x", padx=8, pady=5)

        def reload_entries():
            entries.delete(0, "end")
            for e in store.memory["entries"]:
                entries.insert("end", e)

        def add_manual():
            text = new_entry.get().strip()
            if text:
                store.memory["entries"].append(text)
                store.save_memory()
                new_entry.delete(0, "end")
                reload_entries()

        RoundedButton(addrow, text="Remember", kind="primary",
                      font=(FONT, 10, "bold"),
                      command=add_manual).pack(side="right",
                                               padx=(6, 0))

        def del_entry():
            sel = entries.curselection()
            if sel:
                del store.memory["entries"][sel[0]]
                store.save_memory()
                reload_entries()

        RoundedButton(win, text="Delete selected", kind="quiet",
                      font=(FONT, 9),
                      command=del_entry).pack(anchor="w", padx=10,
                                              pady=4)
        reload_entries()

        tk.Label(win, text="PROPOSED BY THE MODEL — nothing is kept "
                           "until you approve it", bg=BG, fg=ORANGE,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=10,
                                               pady=(12, 2))
        pwrap = BubbleFrame(win, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        pwrap.pack(fill="x", padx=10, pady=4)
        pending = tk.Listbox(pwrap, bg=PANEL2, fg=ORANGE,
                             selectbackground=ORANGE,
                             selectforeground="#000000", bd=0,
                             highlightthickness=0,
                             font=(FONT, 10), height=5)
        pending.pack(fill="both", expand=True, padx=8, pady=6)

        def reload_pending():
            pending.delete(0, "end")
            for p in store.memory["pending"]:
                pending.insert("end", p)

        prow = tk.Frame(win, bg=BG)
        prow.pack(fill="x", padx=10)

        def approve():
            sel = pending.curselection()
            if sel:
                store.memory["entries"].append(
                    store.memory["pending"].pop(sel[0]))
                store.save_memory()
                reload_entries()
                reload_pending()

        def reject():
            sel = pending.curselection()
            if sel:
                store.memory["pending"].pop(sel[0])
                store.save_memory()
                reload_pending()

        RoundedButton(prow, text="Approve", kind="primary",
                      font=(FONT, 10, "bold"),
                      command=approve).pack(side="left")
        RoundedButton(prow, text="Reject", kind="quiet",
                      font=(FONT, 10),
                      command=reject).pack(side="left", padx=6)
        reload_pending()

        tk.Label(win, text="THIS CHAT — WHAT THE MODEL CARRIES "
                           "(origin + compressed topics)", bg=BG,
                 fg=GREEN, font=(FONT, 11, "bold")).pack(
                     anchor="w", padx=10, pady=(12, 2))
        vwrap = BubbleFrame(win, fill=PANEL2, outline=BORDER,
                            radius=RADIUS_PANEL, bg=BG)
        vwrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        view = tk.Text(vwrap, bg=PANEL2, fg=GREEN_DIM, bd=0,
                       highlightthickness=0,
                       font=(FONT, 9), wrap="word", height=7)
        view.pack(fill="both", expand=True, padx=8, pady=6)
        chat = self.current
        if chat:
            if chat.get("origin"):
                view.insert("end", "ORIGIN (pinned, never compressed):\n"
                            "User: %s\nAssistant: %s\n\n"
                            % (chat["origin"]["user"],
                               chat["origin"]["assistant"]))
            view.insert("end", "KEY TOPICS (compressed):\n" +
                        (chat.get("topics") or "(nothing compressed yet)"))
        view.configure(state="disabled")


def acquire_lock(path):
    """Single-instance lock, per platform: flock on Linux,
    msvcrt.locking on Windows. Returns the open file (keep it
    referenced - the lock dies with it) or None when another
    instance already holds it."""
    f = open(path, "w")
    try:
        if IS_WINDOWS:
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def find_repo():
    """The Nexus Chat git checkout on this machine, if any: the
    NEXUS_REPO override, the path the installer recorded in
    DATA_DIR/repo.txt, or the conventional ~/Nexus-Chat clone."""
    cands = []
    env = os.environ.get("NEXUS_REPO")
    if env:
        cands.append(env)
    try:
        with open(os.path.join(DATA_DIR, "repo.txt")) as f:
            cands.append(f.read().strip())
    except OSError:
        pass
    cands.append(os.path.join(os.path.expanduser("~"), "Nexus-Chat"))
    for c in cands:
        if c and os.path.isdir(os.path.join(c, ".git")):
            return c
    return None


def installed_app_cmd():
    """Command that launches the installed app, for the Update
    window's Relaunch button. None if the install is not where
    the installers put it."""
    if IS_WINDOWS:
        path = os.path.join(os.path.dirname(DATA_DIR),
                            "nexus-chat.py")
        if not os.path.isfile(path):
            return None
        pyw = os.path.join(os.path.dirname(sys.executable),
                           "pythonw.exe")
        return [pyw if os.path.isfile(pyw) else sys.executable,
                path]
    path = os.path.join(os.path.expanduser("~"), ".local", "bin",
                        "nexus-chat.py")
    if not os.path.isfile(path):
        repo = find_repo()
        path = os.path.join(repo, "nexus-chat.py") if repo else None
    if not path or not os.path.isfile(path):
        return None
    return [sys.executable, path]


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    lock_path = os.path.join(DATA_DIR, ".lock")
    lock_file = acquire_lock(lock_path)
    if lock_file is None:
        print("Nexus Chat is already running.")
        return
    import tkinter as tk
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
