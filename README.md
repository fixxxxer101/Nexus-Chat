# Nexus Chat

A local AI chat desktop app for the Raspberry Pi 5. Black, green and
orange. It talks to [Ollama](https://ollama.com) running on the same
machine — no accounts, no cloud, nothing leaves the Pi.

## Features

- **Thinking traces, when the model thinks.** Qwen3 replies carry
  a saved thinking trace, shown as a collapsible **▸ Thinking**
  block — click to read exactly how the model reasoned, click
  again to fold it away. There is deliberately **no thinking
  on/off toggle**: Qwen3 in no-think mode still narrates its
  reasoning inside the answer, so a toggle would be a lie. For a
  model that never thinks, pick **qwen2.5:3b** in the model
  picker — it just answers.
- **Glass box.** The **System** button shows the system prompt —
  and lets you edit and save it — plus a live preview of the
  *exact* context the model receives for the open chat: your
  prompt, the appended long-term memory, the pinned origin, the
  compressed-topics note, and the messages. Nothing hidden.
- **Prompt presets.** Save named system prompts in the System
  window, delete them, click to use one — and switch between
  them right in the main window from the **Prompt** picker next
  to the model picker. The header always shows which prompt is
  live: a preset name, **Custom** for unsaved edits, or
  **Default**.
- **Real markdown rendering.** Fenced code renders as an inset
  code box with the language labelled and a **Copy** button;
  tables align in monospace with right-aligned numbers;
  headings, bold and inline code all look the way the model
  meant them.
- **Floating cards.** The Menu's Settings submenu toggles
  the window frame - the background around the header,
  sidebar, chat and input cards - between Black and
  Transparent. On Windows, Transparent makes the cards float
  on the desktop, each keeping a bright green edge. A
  **Content opacity** slider in the same submenu sets how
  solid everything else is, from 30% to 100%.
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
- **Streaming replies**, model picker, Stop button
  mid-generation. Only **qwen2.5:3b** is required — setup
  installs just that one; everything else is optional.
- **Model Manager.** The controller's **Manage models** button
  lists what's on the machine (with sizes) and a catalog of
  optional downloads — Qwen3, GPT-OSS, Mistral, Gemma, the
  coders, vision models — with live download progress and
  delete for anything except the required model. A built-in
  **Hugging Face search** finds any GGUF repo, with a quant
  picker per result (Q4_K_M by default).
- **One Menu, thinking levels.** The header's **Menu** button
  holds the windows (System, Memory, Ollama, Models), Update,
  and a **thinking level** setting remembered per model —
  low / medium / high for gpt-oss, off / on for Qwen3-class
  models, exactly what each model supports. The **Prompt**
  picker sits beside the model picker, with built-in presets
  (Deep Thinker, Creative Partner, Code Mentor) and a Blank
  option that sends no system prompt at all.
- **Modern rounded theme.** Pill-shaped buttons, floating
  rounded cards for the header, sidebar and input bar, big soft
  chat bubbles, and every text and list panel in the windows
  wrapped in a rounded frame — no sharp corners anywhere.
- **Ollama controller built in.** The header's **Ollama** button
  opens the controller panel: live service status, which model is
  loaded and how much RAM it holds, **Start**, **Stop** (frees
  ALL its RAM) and **Unload model** buttons, and the way into
  the Model Manager.

## Setup on the Pi (Linux)

One script does everything — Ollama, the service check, the models,
and the app — detecting and skipping whatever already exists:

```
bash setup.sh
```

(`install.sh` on its own just reinstalls the app and its desktop
icon.) Then click the **Nexus Chat** icon on the desktop.

## Setup on Windows

Needs Python 3 (with Tk — the standard python.org installer
includes it). Clone this repo, then double-click **`setup.bat`**:
it installs Ollama if it's missing (the official installer, which
you click through once), starts it, pulls the models, installs
the app to `%LOCALAPPDATA%\NexusChat`, and puts a **Nexus Chat**
shortcut on the desktop. `install.bat` reinstalls just the app.
The Ollama controller works there too — Start launches Ollama,
Stop kills it and frees all its RAM.

## Updating

The app is versioned: the header shows its version next to the
title, and **every shipped change bumps it** — a feature bumps
the middle number (1.1.0), a fix bumps the last (1.0.1). The
full history is in [CHANGELOG.md](CHANGELOG.md).

The header Menu's **Update Nexus Chat…** entry does it from
inside the app: it runs setup in your git checkout (which
pulls the latest code first), streams the output into a
window, and offers a Relaunch when it's done. No terminal
needed, on either platform. The installers record the
checkout's path (`repo.txt` in the data dir) so it can
always be found.

## Where things live

- Linux — App: `~/.local/bin/nexus-chat.py`; data:
  `~/.local/share/nexus-chat/`; log:
  `~/.local/state/nexus-chat.log`
- Windows — App: `%LOCALAPPDATA%\NexusChat\nexus-chat.py`;
  data: `%LOCALAPPDATA%\NexusChat\data\`

Pure Python 3 + Tkinter + urllib — no extra packages.
Backend override for testing: `NEXUS_OLLAMA=http://host:port`.

By Trinity Nexus.
