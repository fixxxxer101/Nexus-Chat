# Nexus Chat — version history

Versions are numbered against the git history: the first
release is 1.0.0, a feature bumps the middle number, a fix
bumps the last. Every change from 1.9.0 on bumps the version
in the same commit.

## 1.9.1 — 2026-11-21
Fix: bevels on every raised surface — a light line along the
top/left edges and a dark line along the bottom/right (green
family, amber for the user's bubbles, orange for primary
buttons), so the stacked layers read as separate levels
instead of blending together.

## 1.9.0 — 2026-11-21
Visible versioning: the version shows in the header, the
window title, and the Update window. (This release was first
stamped 1.0.0; the number was corrected to what the history
below earns.)

## 1.8.1 — 2026-11-21
Fix: the Update window's buttons were clipped out of the
window by an oversized log box — the update could not be
started. Log box sized sanely; regression test added.

## 1.8.0 — 2026-11-21
Windows port (one codebase: lock, paths, fonts, and the
Ollama controller branch per OS; setup.bat / install.bat /
setup_win.py) and the in-app Update button.

## 1.7.0 — 2026-11-21
The full modern rounded look: pill buttons, floating rounded
cards for header / sidebar / input bar, big soft bubbles,
rounded panels around every text and list widget.

## 1.6.1 — 2026-11-21
Fix: brighter scrollbar — a solid green thumb you can see.

## 1.6.0 — 2026-11-21
System-prompt presets: save / delete / pick in the System
window, plus a Prompt picker in the header beside the model
picker.

## 1.5.0 — 2026-11-21
setup.sh updates itself first (git pull + re-exec), so one
command is the whole install / update / repair path.

## 1.4.0 — 2026-11-21
Thinking toggle removed (Qwen3 narrates its reasoning in
no-think mode, so the toggle could not be honest), qwen2.5:3b
added as the non-thinking model, and the glass box: editable
system prompt + a live preview of the exact context the
model receives.

## 1.3.0 — 2026-11-21
The Ollama controller moves inside Nexus Chat as a panel
behind the header's Ollama button; the standalone controller
app is removed.

## 1.2.0 — 2026-11-21
Modern rounded UI (canvas-drawn buttons, chat bubbles) and
the Ollama Controller (Start / Stop / Unload, RAM readout).

## 1.1.2 — 2026-11-21
Fixes: thinking-OFF narration handled, stream timeout raised
from 120 s to 1800 s, timed-out streams hang up instead of
pinning the CPU, stream errors render in the chat.

## 1.1.1 — 2026-11-21
Fixes: thinking traces captured and collapsible, custom icon,
desktop shortcut marked trusted.

## 1.1.0 — 2026-11-21
setup.sh: one idempotent script does the whole stack.

## 1.0.0 — 2026-11-21
Nexus Chat v1: local Qwen3 desktop chat — streaming replies,
thinking traces, sidebar chat logs, long-term memory (manual
+ model-proposed / user-approved), rolling context with
selective compression and a pinned origin.
