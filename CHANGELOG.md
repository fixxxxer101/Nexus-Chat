# Nexus Chat — version history

Versions are numbered against the git history: the first
release is 1.0.0, a feature bumps the middle number, a fix
bumps the last. Every change from 1.9.0 on bumps the version
in the same commit.

## 1.29.0 — 2026-11-22
Error Log window (Menu → Error Log…), at Clint's ask:
shows the app's log file (path printed in the window),
newest at the bottom, with Refresh, Copy all, and a
Copy last error button that grabs just the most recent
traceback - built for pasting straight to Vox. To make
the log worth reading, errors are now captured INTO it:
UI callback exceptions and worker-thread exceptions
are hooked and written with full tracebacks (before,
they went to a console the Windows app does not have),
and every launch writes a versioned start line so
sessions are easy to tell apart in a paste.

## 1.28.0 — 2026-11-21
Three live reports from the first real image run, fixed:
leaving the seed blank crashed generation (a missing
import behind the random-seed path) - blank now means
random, and the seed used is recorded as before; a mode
switch could leave the sidebar card's outline drawn at
a mid-relayout size on Windows - every layout card now
re-settles after a switch; and the Vulkan engine build
crashed on a Radeon 780M right after loading the model
(code 3221226505) - setup now also installs the CPU
build alongside any GPU build, and when a generation
dies the app retries it once on the CPU build,
remembers the fallback (the engine line says so), and
Image Models offers "Retry GPU build" to try the GPU
again. Image models also get their OWN manager, as
asked (Menu → Image Models…; the studio button opens it
too, and the chat Model Manager is chat-only again):
it manages SD checkpoints, VAE encoders and LoRAs -
Hugging Face search by kind (models / VAEs / LoRAs,
each with its own file rules and download folder),
linked folders classified by their layout (a ComfyUI
models folder's checkpoints / vae / loras subfolders
are recognised), downloaded VAEs and LoRAs listed with
delete. The studio gains a VAE picker (Built-in = the
checkpoint's own) passed to the engine as --vae, and a
LoRA Insert… that drops a <lora:name:0.8> tag into the
prompt; the runner stages the named LoRAs from wherever
they live into one folder for the engine's
--lora-model-dir. Generation records now include the
VAE, and picking a history entry restores it.

## 1.27.0 — 2026-11-21
Image generation: a Chat / Image switch at the top of
the sidebar. The Image studio generates pictures with
sd-cli (stable-diffusion.cpp) - a standalone engine,
no ComfyUI, no Python stack, so it works on any
machine. Setup installs the build that matches the
machine: CUDA for NVIDIA, Vulkan for AMD/Intel, CPU
as the fallback on Windows; built from source on
Linux. DreamShaper 8 (SD 1.5) is a REQUIRED model,
downloaded by setup and verified against the
publisher's SHA256 hash. The studio has prompt and
negative prompt, size / steps / CFG / sampler / seed
(with the used seed recorded), live step progress
with the engine's own log line visible, Cancel, and
a history of generations - each saved with its full
settings, and picking one reloads them all. The
Model Manager gains an Image models section: the
baseline and an optional catalog (DreamShaper 8 LCM
for speed, DreamShaper XL Turbo and SDXL Base for
PCs), Hugging Face search for single-file image
checkpoints, and image model folders whose
checkpoints are used in place - a ComfyUI folder
works as a plain folder of files.

## 1.26.0 — 2026-11-21
Renamed: Nexus Chat is now Nexus Gate, matching the
renamed GitHub repository. The header, window
titles, menus, installer and shortcuts all carry the
new name, the self-update check reads from the
Nexus-Gate repository, and the Windows setup removes
the old Nexus Chat desktop shortcut when it installs
the Nexus Gate one. Nothing else moves: the app
file, the data folders and every chat, setting and
knowledge base stay exactly where they were, so the
rename costs nobody their history. (Earlier entries
in this changelog keep the old name - they describe
what the app was called then.)

## 1.25.1 — 2026-11-21
The Knowledge Bases window no longer has a "Get
embedding model" button. Since the model is a
required download, the window simply verifies it
instead: on open (and after any indexing error) it
checks the model is installed and runs a live embed
probe, and the status line reports the result -
"installed and ready", "not installed" (run setup
again), or "not responding".

## 1.25.0 — 2026-11-21
nomic-embed-text is a required model now, not an
optional extra: Knowledge Bases need it at all times,
so setup force-downloads it alongside qwen2.5:3b on
every install and update (both setup.sh and the
Windows setup, which reads the required list from
the app). In the Model Manager it carries the
REQUIRED badge and cannot be deleted, same as
qwen2.5:3b, and it no longer appears in the header's
chat-model picker - it is infrastructure, not a chat
model.

## 1.24.0 — 2026-11-21
Knowledge Bases (RAG) and an adjustable context size.

Knowledge Bases: a base is a label and a folder
(Menu > Knowledge Bases...). Its text files are
chunked and embedded locally with nomic-embed-text
(new in the model catalog, and offered for download
in the Knowledge Bases window when missing), and the
index lives in the app's data folder. Each chat picks
its base in the header's Knowledge picker; when you
send a message, the best-matching chunks ride along
with your question, and the reply shows a Sources
line naming the files they came from. Removing a
base deletes only its index, never your files.

Context size: Menu > Settings > Context size -
4096 (the Pi-safe default), 8192, 16384 or 32768
tokens. Every chat call and the compression budget
follow the setting, so bigger machines can use the
room they have.

## 1.23.0 — 2026-11-21
The app checks for its own updates. A few seconds
after starting, and then on an interval (every
10 minutes by default), it reads the VERSION from
the head of nexus-chat.py on GitHub's main branch -
only the first chunk of the file is downloaded. When
a newer version exists, the version text in the
header turns orange and reads "vX.Y.Z (Update
Available)"; clicking it opens the Update window.
Checks that fail (offline, unreachable) are silent -
no answer, no alarm. The interval is set under
Menu > Settings > Update checks: Off, 5, 10 or
30 minutes, 1 or 6 hours.

## 1.22.0 — 2026-11-21
Bubbles run the full width of the chat now - user and
assistant alike - and the text wraps at the full
available width instead of the old narrower measure,
so nothing is squished into a content-sized box.
HTML line breaks are respected for formatting: <br>,
<br/> and <BR> in message text render as real line
breaks (code blocks stay verbatim, and the stored
text keeps the original tags).

## 1.21.2 — 2026-11-21
Two fixes. The 1.21.1 bubbles lost their fills
entirely: the content frame inside the bubble canvas
is opaque and covered the whole bubble, hiding the
painted background beneath it. The content is now
inset 6px on every side, so the painted rounded rect
shows as the bubble's corners and edge ring around
the frame's own matching fill. And the dialogs
(Update, Model Manager, and the rest) now get the
app icon and the system-theme title bar like the
main window - the theme is re-applied just after a
dialog appears, because Windows resets it when set
before the window is first shown.

## 1.21.1 — 2026-11-21
Chat bubbles rebuilt on a sound mechanism. The bubble
is now a single canvas that carries its content and
paints its own background, sizing itself from the
content's requested size - the same pattern as the
header buttons, which render correctly everywhere.
The old design (a background canvas placed inside a
separate frame) kept losing the bubbles' bottom halves
on Windows through three rounds of patches; the cards
and manager rows, which were never reported broken,
keep the old frame design.

## 1.21.0 — 2026-11-21
The window title bar now follows the system theme: on
Windows it reads the AppsUseLightTheme setting and sets
the DWM immersive dark-mode attribute to match - dark on
a dark-mode system, light on a light one - for the main
window and every dialog the app opens. No more white
title bar over a dark app. (Linux/Pi: the window manager
owns decorations; nothing changes there.)

## 1.20.4 — 2026-11-21
Bubble bottoms still unpainted (user and assistant
bubbles alike, settled state, annotated screenshot):
the text and spacing were always right - only the
painted background stopped partway. A canvas shows only
what fits inside its own box, so a background canvas
left shorter than its drawing clips the rest away.
Content-sized frames (bubbles, rows, code boxes) now
draw to their content's full requested height and pin
the background canvas to that height in pixels on every
redraw, so the painted bubble always covers the whole
message. The four layout cards keep layout-driven
sizing.

## 1.20.3 — 2026-11-21
A finished reply's bubble shrank in width the moment the
stream ended: the rich renderer created its labels at a
fixed 600px wrap while everything else uses the live
width (canvas width - 130), and nothing re-applied the
live width until the next window resize - invisible in a
narrow window, glaring in a wide one. Labels are now
born at the live wrap width, so a bubble keeps its width
from first token to finished render - and its height no
longer jumps at the finish either, which is the same
relayout the short-outline report rides on. Stream
finishes also log the bubble's frame size, requested
size, canvas height and drawn outline bottom, so any
remaining outline fault names its layer in the log.

## 1.20.2 — 2026-11-21
Bubble outlines could freeze at an earlier, shorter
height on Windows - a tall reply's last lines spilled
below an unclosed border. The redraw now takes its size
from the Configure event itself (winfo can lag during a
relayout), the underlay canvas's own resize is a second
draw trigger, and every card and bubble redraws once more
at idle after a chat opens, a stream finishes rendering,
or a thinking section toggles - so the final outline
always matches the final size. Header buttons got the
same treatment, and a button's click now tests against
the drawn pill itself, so the hitbox is exactly the
button you see.

## 1.20.1 — 2026-11-21
Model Locations scanning, made visible: a Scan now button
re-scans on demand (adding a folder and opening the
manager already scan automatically - no restart has ever
been needed), every added folder shows how many GGUF
files the scan found under it, the scan is written to the
app log, and linked subfolders (junctions/symlinks) are
now followed, with a visited-folder guard so a link cycle
can't loop the scan.

## 1.20.0 — 2026-11-21
Model Locations: GGUF models that already live somewhere
else - an LM Studio folder, a ComfyUI folder, any folder -
now run IN PLACE, with no second copy. The Model Manager
takes any number of folders, scans them (subfolders
included, split GGUFs grouped), and "Use in place"
registers a file with Ollama by hardlinking it into the
store under its own hash and writing the manifest by hand
- zero extra disk, no restart, the original never touched.
Every model in the manager now shows WHERE it lives ("In
place - <full path>" or "Ollama store - <folder>"), so a
duplicate can be removed from the right place: an in-place
model's Remove only unregisters it (its blobs are dropped
only when no other model references them; the file
stays), while a store model's Delete removes Ollama's
copy. Where a file cannot be shared with the store
(another drive, a FAT/exFAT card), registration refuses
with the reason rather than silently copying gigabytes.

## 1.19.1 — 2026-11-21
The from-scratch installer is renamed to
Nexus_Chat_Installer_Windows.bat. Same script, new name.

## 1.19.0 — 2026-11-21
from-scratch.bat: one double-click installs Nexus Chat on
a fresh Windows PC. It installs Python 3, Git for Windows
and Ollama when they're missing (quiet installers from the
official sources), clones this repo to
%USERPROFILE%\Nexus-Chat, hands off to setup.bat (model
pull, app install, desktop shortcut), and launches the
app. Idempotent: re-running skips whatever is done, and
every failure path says what to fix and that re-running is
safe.

## 1.18.1 — 2026-11-21
The window opens in front: at startup it raises itself,
takes focus, and holds topmost for a fraction of a second
so the window manager honours the raise - then lets go and
behaves like a normal window.

## 1.18.0 — 2026-11-21
Three frame fixes in one: (1) the magenta outline is gone -
a card's backing colour lives on its underlay canvas as
well as its frame, and switching Frame modes now updates
both (before, the canvas kept the old punch colour, tracing
every card in magenta after a toggle back to Black).
(2) The four main cards get a bright green perimeter edge,
so they keep their definition when the frame vanishes.
(3) A content opacity slider (Menu > Settings > Content
opacity…): how solid everything that isn't the frame is,
30-100%, live while you drag, remembered across restarts.
With Frame: Transparent the frame stays fully gone at any
slider value; with Frame: Black the whole window fades
together (window alpha is per-window in Tk).

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
