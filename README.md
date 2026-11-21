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

## Setup on the Pi

1. Install Ollama and pull the models:

   ```
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:4b
   ollama pull qwen3:1.7b
   ```

2. Install Nexus Chat:

   ```
   bash install.sh
   ```

3. Click the **Nexus Chat** icon on the desktop.

## Where things live

- App: `~/.local/bin/nexus-chat.py`
- Chats, memory, settings: `~/.local/share/nexus-chat/`
- Error log: `~/.local/state/nexus-chat.log`

Pure Python 3 + Tkinter + urllib — no extra packages.
Backend override for testing: `NEXUS_OLLAMA=http://host:port`.

By Trinity Nexus.
