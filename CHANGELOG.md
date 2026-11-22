# Nexus Chat — version history

Versions are numbered against the git history: the first
release is 1.0.0, a feature bumps the middle number, a fix
bumps the last. Every change from 1.9.0 on bumps the version
in the same commit.

## 1.17.0 — 2026-11-21
The transparency moves to where it was meant to be: the
FRAME around the cards. Menu > Settings > Frame now toggles
the window's outer background - the root and the seams
between the header, sidebar, chat and input cards -
between Black and Transparent. Transparent makes the cards
float on the desktop; the cards and everything inside them,
chat included, stay solid. (The 1.16 setting aimed at the
chat area instead; the saved setting carries over.)

## 1.16.1 — 2026-11-21
Fix: on Windows, turning the chat background setting off
passed an empty string to Tk's -transparentcolor, which on
some builds keys transparency on the window's background
colour instead - so the app's outer seams (the root
background around the cards) went transparent while the
chat area stayed solid. The off state now uses a dummy key
colour that is never drawn, so nothing punches through
when transparency is off, and only the chat area punches
when it is on.

## 1.16.0 — 2026-11-21
Assistant messages render their markdown properly. Fenced
code becomes an inset code box with the language labelled
and a Copy button that puts the exact code on the
clipboard; markdown tables render aligned in monospace
with a header rule and right-aligned numeric columns;
headings get their size and weight; bold and inline-code
markers no longer litter the text (Tk labels can't style
inline spans, so paragraphs keep the words and drop the
markers). While a reply streams it shows raw, and the
finished message re-renders rich. User messages stay
verbatim.

Also: a Settings submenu in the header Menu toggles the
chat background - the area behind the bubbles - between
Black and Transparent. Transparent paints that area with a
punch-through key colour and marks it transparent on the
window, so on Windows the desktop shows through around the
bubbles. (Tk under X11 has no per-colour punch-through, so
on the Pi the area simply stays dark.)

## 1.15.0 — 2026-11-21
The Prompt picker returns to the header beside the model
picker (it spent one release inside the Menu; Manage
prompts… stays in the Menu as well), and the picker gains
built-in presets: Deep Thinker, Creative Partner and Code
Mentor - three different defaults to test against each
other - plus Blank, which sends no system prompt at all
(the model receives no system message; long-term memory
rides in that message, so it is out too while Blank is
active). Saving a user preset under a built-in's name
shadows it. Also in this release: the sidebar's Update
button moves into the Menu as "Update Nexus Chat…".

## 1.14.0 — 2026-11-21
A downloads strip pinned to the base of the Model Manager:
whatever is downloading right now - catalog or Hugging
Face - with a progress bar, percent, downloaded / total,
live speed and estimated time left, rendered from the
app-level download state. Open the manager and it's just
there; no searching or scrolling to find your download
again. When nothing is running it says so.

## 1.13.0 — 2026-11-21
Three additions. (1) Hugging Face search in the Model
Manager: search GGUF repos by name or keyword, get the top
20 by downloads, pick a quant per result (Q4_K_M by
default, every quant with its real size), and download -
hf.co models use the same pull machinery, so background
downloads, the header picker and Delete all apply.
(2) A thinking level setting, per model, in the Menu: the
levels offered are the ones the model supports - low /
medium / high for gpt-oss (which has no off), off / on for
Qwen3 and DeepSeek-R1, nothing for models that never
think. (3) The header's separate Memory / System / Ollama
/ Prompt buttons are now one Menu button holding all of
them plus the Model Manager; the header keeps the title,
the model picker and the status.

## 1.12.0 — 2026-11-21
Model downloads now belong to the app, not the Model
Manager window: close the manager mid-download and the
pull keeps going in the background, the finished model
still lands in the header picker, and reopening the
manager shows the download mid-flight with its live
progress and Cancel button, exactly where it is.

## 1.11.0 — 2026-11-21
The Model Manager (the Ollama panel's new "Manage models"
button): an ON THIS MACHINE list of everything installed,
with sizes, and a catalog of optional models to download —
the Qwen3s, GPT-OSS 20B, the Mistral family, Gemma 3 / 3n,
the Qwen coders, and vision models (Gemma 3, Qwen3-VL,
LLaVA, Moondream) — each with its real registry-verified
download size and a note where a model is PC-class rather
than Pi-class. Downloads stream from Ollama with live
progress, one at a time, cancellable (a partial pull
resumes), and a finished model lands in the header picker.
Any installed model can be deleted (two-click confirm) —
except the required one. And the required set is now just
qwen2.5:3b: setup installs only it (a ~1.9 GB first
install), and everything else is an optional download,
the two Qwen3s included.

## 1.10.1 — 2026-11-21
Fix (Windows): updating from inside the app no longer opens
a terminal window. The app runs without a console, so the
cmd child got a brand-new one; it now spawns with
CREATE_NO_WINDOW and the whole update — setup, git pull,
model pulls — stays inside the Update window's log, exactly
like the Pi. The controller's taskkill got the same flag so
stopping Ollama doesn't flash a console either.

## 1.10.0 — 2026-11-21
The chat window is contained: the transcript now lives in
its own rounded, beveled card beside the sidebar card, tops
aligned, instead of floating loose on the window background.
And the chat scrollbar is rounded — the stock Tk scrollbar
is a square-ended rectangle, so it is replaced with a
canvas-drawn one: pill trough, pill thumb (green, brighter
while dragging), drag / trough-click paging / wheel all as
before. The default system prompt now says the app is
designed to run on a Raspberry Pi 5 and beyond. Building
this also exposed and fixed two scroll bugs that were
already there: a stale "at bottom" flag could yank the view
back down after scrolling up (Tk delivers the scroll
notification late; the stick-to-bottom check now reads live
geometry), and switching from a long chat to a short one
left the old tall scroll region behind (open_chat now
settles the region itself).

## 1.9.2 — 2026-11-21
Fix: the bevel's light edge now runs all the way around each
surface — the two-tone version (light top, dark bottom) read
as lit from above only; the full light outline is the look
asked for.

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
