# Nexus Chat

A local AI chat desktop app for the Raspberry Pi 5. Black, green and
orange. It talks to [Ollama](https://ollama.com) running on the same
machine — no accounts, no cloud, nothing leaves the Pi.

## Features

- **Qwen3 with a thinking toggle.** Thinking on or off per the header
  switch. Every reply's thinking trace is saved and shown as a
  collapsible **▸ Thinking** block — click to read exactly how the
  model reasoned, click again to fold it away.
- **Chat logs.** Every conversation auto-saves and lists in the
  sidebar. Reopen any of them any time.
- **Long-term memory, both modes.**
  - *Manual:* open **Memory**, type what it should remember, edit or
    delete entries any time.
  - *Automatic:* the model proposes durable facts after chats. They
    wait in a pending list — **nothing is kept until you approve it**.
- **Rolling context with selective compression.** When a chat grows
  past the context window, older turns are folded into a key-topics
  note: weighted by what is talked about *most*, decisions and facts
  kept, one-off tangents pruned. The **origin** of the chat — its
  first exchange, the thing that led to where you are — is pinned
  and never compressed away. Compression only changes what the model
  sees; the saved log always keeps every word. The Memory window
  shows exactly what the model currently carries for the open chat.
- **Streaming replies**, model picker (Qwen3 4B default, 1.7B fast
  mode), Stop button mid-generation.
- **Modern rounded theme.** Canvas-drawn rounded buttons and
  chat-bubble messages — no sharp corners anywhere.
- **Ollama Controller** (installed alongside): a small panel that
  shows whether Ollama is running, which model is loaded and how
  much RAM it holds, with **Start**, **Stop** (frees ALL its RAM)
  and **Unload model** buttons. Its own desktop icon — a power
  symbol.

## Setup on the Pi

One script does everything — Ollama, the service check, both models,
and the app — detecting and skipping whatever already exists:

```
bash setup.sh
```

Re-running it after a `git pull` is also how you update: only the
missing pieces happen. (`install.sh` on its own just reinstalls the
app and its desktop icon.)

Then click the **Nexus Chat** icon on the desktop.

## Where things live

- App: `~/.local/bin/nexus-chat.py`
- Ollama Controller: `~/.local/bin/ollama-controller.py`
- Chats, memory, settings: `~/.local/share/nexus-chat/`
- Error log: `~/.local/state/nexus-chat.log`

Pure Python 3 + Tkinter + urllib — no extra packages.
Backend override for testing: `NEXUS_OLLAMA=http://host:port`.

By Trinity Nexus.
