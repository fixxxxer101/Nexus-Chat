#!/usr/bin/env python3
"""Nexus Chat - a local AI chat desktop app for the Raspberry Pi 5.

Talks to Ollama running on the same machine (Qwen3 by default).
Black / green / orange. No accounts, no cloud: chats, memory and
logs all live on the Pi under ~/.local/share/nexus-chat/.

Features (Clint's spec, 2026-11-21):
  - Qwen3 thinking mode with an on/off toggle; each reply's thinking
    trace is a collapsible block (click to expand/collapse), saved
    in the chat log so old reasoning can be re-read.
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

import fcntl
import json
import os
import queue
import sys
import threading
import time
import urllib.request
import urllib.error

APP_NAME = "Nexus Chat"
OLLAMA = os.environ.get("NEXUS_OLLAMA", "http://localhost:11434")
DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share",
                        "nexus-chat")
CHATS_DIR = os.path.join(DATA_DIR, "chats")
MEMORY_PATH = os.path.join(DATA_DIR, "memory.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOG_PATH = os.path.join(os.path.expanduser("~"), ".local", "state",
                        "nexus-chat.log")
DEFAULT_MODELS = ["qwen3:4b", "qwen3:1.7b"]
NUM_CTX = 4096
# context budget (rough tokens, chars/4): compress when the assembled
# context passes COMPRESS_AT; always keep the last KEEP_RAW messages
# (after the origin pair) word-for-word.
COMPRESS_AT = 2700
KEEP_RAW = 6
PROPOSE_EVERY = 8          # user turns between memory-proposal passes

# ---- theme: black, green lettering, orange highlight ----
BG = "#000000"
PANEL = "#070b07"
PANEL2 = "#0d130d"
GREEN = "#35ff69"
GREEN_DIM = "#2ea35c"
GREEN_FAINT = "#1c5c36"
ORANGE = "#ff8c1a"
ORANGE_DIM = "#a35c10"
THINK_GREEN = "#57c785"
ERROR = "#ff5a3c"
FONT = "DejaVu Sans"
MONO = "DejaVu Sans Mono"

SYSTEM_PROMPT = (
    "You are the assistant inside Nexus Chat, a private local chat "
    "app running entirely on the user's own Raspberry Pi. Be direct, "
    "accurate and concise unless asked for depth. Everything here is "
    "offline and private."
)

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


class Streamer:
    """Runs one streaming /api/chat call on a thread; events go to a
    queue as ("thinking", text), ("content", text), ("done", None),
    ("error", message)."""

    def __init__(self, model, messages, think, events):
        self.model = model
        self.messages = messages
        self.think = think
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
            payload["think"] = bool(self.think)
        req = urllib.request.Request(
            OLLAMA + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            self._resp = urllib.request.urlopen(req, timeout=120)
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
                    self.events.put(("content", msg["content"]))
                if data.get("error"):
                    self.events.put(("error", str(data["error"])))
            self.events.put(("done", None))
        except Exception as e:  # connection refused, closed on stop, ...
            if self.stopped.is_set():
                self.events.put(("done", None))
            else:
                self.events.put(("error", str(e)))


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
    system = SYSTEM_PROMPT
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


# ---------------------------------------------------------------- GUI

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
        self.think = tk.BooleanVar(value=bool(self.store.settings.get(
            "think", False)))
        self._at_bottom = True

        root.title(APP_NAME)
        root.geometry("1040x700")
        root.minsize(780, 540)
        root.configure(bg=BG)
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
        head = tk.Frame(self.root, bg=PANEL, height=46)
        head.pack(side="top", fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="NEXUS CHAT", bg=PANEL, fg=GREEN,
                 font=(FONT, 13, "bold")).pack(side="left", padx=12)
        self.status = tk.Label(head, text="", bg=PANEL, fg=GREEN_DIM,
                               font=(FONT, 9))
        self.status.pack(side="right", padx=10)
        tk.Button(head, text="Memory", bg=PANEL2, fg=GREEN,
                  activebackground=PANEL, activeforeground=ORANGE,
                  bd=0, highlightthickness=1, highlightbackground=GREEN_FAINT,
                  font=(FONT, 10, "bold"), padx=10,
                  command=self.open_memory).pack(side="right", pady=8)
        self.think_btn = tk.Button(head, text="", bg=PANEL2, fg=GREEN,
                                   activebackground=PANEL,
                                   activeforeground=ORANGE, bd=0,
                                   highlightthickness=1,
                                   highlightbackground=GREEN_FAINT,
                                   font=(FONT, 10, "bold"), padx=10,
                                   command=self._toggle_think)
        self.think_btn.pack(side="right", padx=8, pady=8)
        self._paint_think_btn()
        self.model_menu = tk.OptionMenu(head, self.model, self.model.get())
        self.model_menu.configure(bg=PANEL2, fg=GREEN,
                                  activebackground=PANEL,
                                  activeforeground=ORANGE, bd=0,
                                  highlightthickness=1,
                                  highlightbackground=GREEN_FAINT,
                                  font=(FONT, 10))
        self.model_menu.pack(side="right", pady=8)
        tk.Label(head, text="Model", bg=PANEL, fg=GREEN_DIM,
                 font=(FONT, 9)).pack(side="right", padx=(0, 4))

        body = tk.Frame(self.root, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        side = tk.Frame(body, bg=PANEL, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Button(side, text="+  New Chat", bg=ORANGE, fg="#000000",
                  activebackground=ORANGE, activeforeground="#000000",
                  bd=0, font=(FONT, 11, "bold"), pady=4,
                  command=self.new_chat).pack(fill="x", padx=8, pady=8)
        self.chat_list = tk.Listbox(
            side, bg=PANEL, fg=GREEN, selectbackground=ORANGE,
            selectforeground="#000000", bd=0, highlightthickness=0,
            font=(FONT, 10), activestyle="none")
        self.chat_list.pack(fill="both", expand=True, padx=4)
        self.chat_list.bind("<<ListboxSelect>>", self._sidebar_pick)
        tk.Button(side, text="Delete chat", bg=PANEL2, fg=GREEN_DIM,
                  activebackground=PANEL, activeforeground=ERROR, bd=0,
                  font=(FONT, 9), command=self.delete_current
                  ).pack(fill="x", padx=8, pady=8)

        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(main, bg=BG, bd=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(main, orient="vertical",
                                      command=self.canvas.yview)
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

        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(side="bottom", fill="x")
        self.input = tk.Text(bar, height=3, bg=PANEL2, fg=GREEN,
                             insertbackground=ORANGE, bd=0,
                             highlightthickness=1,
                             highlightbackground=GREEN_FAINT,
                             font=(FONT, 11), wrap="word")
        self.input.pack(side="left", fill="both", expand=True,
                        padx=8, pady=8)
        self.input.bind("<Return>", self._enter)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.input.focus_set()
        self.send_btn = tk.Button(bar, text="Send", bg=ORANGE,
                                  fg="#000000", activebackground=ORANGE,
                                  bd=0, font=(FONT, 12, "bold"),
                                  width=7, command=self._send_or_stop)
        self.send_btn.pack(side="right", padx=8, pady=8)

    def _paint_think_btn(self):
        if self.think.get():
            self.think_btn.configure(text="Thinking: ON", fg=ORANGE)
        else:
            self.think_btn.configure(text="Thinking: OFF", fg=GREEN)

    def _toggle_think(self):
        self.think.set(not self.think.get())
        self.store.settings["think"] = bool(self.think.get())
        self.store.save_settings()
        self._paint_think_btn()

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
        frame = tk.Frame(self.flow, bg=BG)
        frame.pack(fill="x", padx=10, pady=4)
        self.blocks.append(frame)
        if role == "user":
            tk.Label(frame, text="YOU", bg=BG, fg=ORANGE,
                     font=(FONT, 9, "bold")).pack(anchor="w")
            accent = ORANGE
        else:
            tk.Label(frame, text="NEXUS", bg=BG, fg=GREEN,
                     font=(FONT, 9, "bold")).pack(anchor="w")
            accent = GREEN
        block = {"frame": frame, "thinking_lbl": None,
                 "thinking_head": None, "open": False}
        self.block_objs.append(block)
        if thinking:
            self._add_thinking(block, thinking)
        lbl = tk.Label(frame, text=content, bg=BG, fg=accent,
                       font=(FONT, 11), justify="left", anchor="w",
                       wraplength=600)
        lbl.pack(fill="x", anchor="w")
        self._wrap_labels.append(lbl)
        block["content_lbl"] = lbl
        return block

    def _add_thinking(self, block, text):
        tk = self.tk
        head = tk.Label(block["frame"], text="▸ Thinking", bg=BG,
                        fg=ORANGE_DIM, font=(FONT, 9, "italic"),
                        cursor="hand2")
        head.pack(anchor="w")
        lbl = tk.Label(block["frame"], text=text, bg=BG,
                       fg=THINK_GREEN, font=(FONT, 10, "italic"),
                       justify="left", anchor="w", wraplength=600)

        def toggle(_e=None, b=block):
            b["open"] = not b["open"]
            if b["open"]:
                b["thinking_lbl"].pack(fill="x", anchor="w",
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
        self.streamer = Streamer(model, ctx, self.think.get(), self.events)
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
        menu = self.model_menu["menu"]
        menu.delete(0, "end")
        for name in (names or DEFAULT_MODELS):
            menu.add_command(
                label=name,
                command=lambda n=name: self.model.set(n))
        if names and self.model.get() not in names:
            self.model.set(names[0])

    def _on_close(self):
        self.store.save_settings()
        self.root.destroy()

    # ---- memory window -------------------------------------------------
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
        entries = tk.Listbox(win, bg=PANEL2, fg=GREEN,
                             selectbackground=ORANGE,
                             selectforeground="#000000", bd=0,
                             highlightthickness=1,
                             highlightbackground=GREEN_FAINT,
                             font=(FONT, 10), height=8)
        entries.pack(fill="x", padx=10, pady=4)

        addrow = tk.Frame(win, bg=BG)
        addrow.pack(fill="x", padx=10)
        new_entry = tk.Entry(addrow, bg=PANEL2, fg=GREEN,
                             insertbackground=ORANGE, bd=0,
                             highlightthickness=1,
                             highlightbackground=GREEN_FAINT,
                             font=(FONT, 10))
        new_entry.pack(side="left", fill="x", expand=True)

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

        tk.Button(addrow, text="Remember", bg=ORANGE, fg="#000000",
                  activebackground=ORANGE, bd=0, font=(FONT, 10, "bold"),
                  command=add_manual).pack(side="right", padx=(6, 0))

        def del_entry():
            sel = entries.curselection()
            if sel:
                del store.memory["entries"][sel[0]]
                store.save_memory()
                reload_entries()

        tk.Button(win, text="Delete selected", bg=PANEL2, fg=GREEN_DIM,
                  activebackground=PANEL, activeforeground=ERROR, bd=0,
                  font=(FONT, 9),
                  command=del_entry).pack(anchor="w", padx=10, pady=2)
        reload_entries()

        tk.Label(win, text="PROPOSED BY THE MODEL — nothing is kept "
                           "until you approve it", bg=BG, fg=ORANGE,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=10,
                                               pady=(12, 2))
        pending = tk.Listbox(win, bg=PANEL2, fg=ORANGE,
                             selectbackground=ORANGE,
                             selectforeground="#000000", bd=0,
                             highlightthickness=1,
                             highlightbackground=GREEN_FAINT,
                             font=(FONT, 10), height=5)
        pending.pack(fill="x", padx=10, pady=4)

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

        tk.Button(prow, text="Approve", bg=ORANGE, fg="#000000",
                  activebackground=ORANGE, bd=0, font=(FONT, 10, "bold"),
                  command=approve).pack(side="left")
        tk.Button(prow, text="Reject", bg=PANEL2, fg=GREEN_DIM,
                  activebackground=PANEL, activeforeground=ERROR, bd=0,
                  font=(FONT, 10),
                  command=reject).pack(side="left", padx=6)
        reload_pending()

        tk.Label(win, text="THIS CHAT — WHAT THE MODEL CARRIES "
                           "(origin + compressed topics)", bg=BG,
                 fg=GREEN, font=(FONT, 11, "bold")).pack(
                     anchor="w", padx=10, pady=(12, 2))
        view = tk.Text(win, bg=PANEL2, fg=GREEN_DIM, bd=0,
                       highlightthickness=1,
                       highlightbackground=GREEN_FAINT,
                       font=(FONT, 9), wrap="word", height=7)
        view.pack(fill="both", expand=True, padx=10, pady=(0, 10))
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


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    lock_path = os.path.join(DATA_DIR, ".lock")
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Nexus Chat is already running.")
        return
    import tkinter as tk
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
