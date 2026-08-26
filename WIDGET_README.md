# TOKI Widget — Hotkey + Voice Edition

> **This is the current and permanent UI** — `main.py` launches
> `main_widget.py` directly, no chat window, and that's staying the
> long-term direction, not a transitional state. "toki_v22" below is
> just old folder-naming framing from an earlier drop-in-patch layout;
> ignore that and the "replaces app.py" framing (`app.py` doesn't exist
> in this codebase anymore) — the technical behavior described below is
> accurate and current.

Drop these three files into your `toki_v22/` folder and run `python main_widget.py`.

---

## Files

| File | Purpose |
|---|---|
| `toki_desktop_mark.py` | Desktop widget (replaces old version) |
| `voice_pipeline.py` | Ctrl+K voice capture (replaces old wake-word version) |
| `main_widget.py` | Entry point — replaces `app.py` for widget-only mode |

---

## Install

```
pip install pynput faster-whisper sounddevice onnxruntime
```

`openWakeWord` is no longer needed.

---

## How it works

### Idle
A tiny 56 px TOKI mark peeks 6 px below the top-centre of your screen.
Barely visible. No chat window anywhere.

### Hover (while idle)
The mark slides fully into view. A panel appears below it listing every
scheduled/timed command with a live countdown and a one-click **✕ cancel** button.
Mouse away → panel closes, mark slides back to notch.

### Ctrl+K — start / extend listening
- **First press**: mark expands to 128 px, slides fully into view, mood → `mysterious`.
  Microphone opens. Recording starts. The widget only ever starts listening
  through this hotkey — hovering alone never opens the mic, it only shows
  the scheduled-commands panel (see above).
- **Quick tap (press + release almost immediately)**: unchanged from before —
  TOKI keeps listening and figures out on its own when you've stopped talking
  (silence hangover, ~1.8 s of real silence ends the recording). Pressing
  Ctrl+K again mid-session resets that silence timer, so you can keep
  re-triggering it to stay alive as long as you want.
- **Hold (press and keep it down while you talk)**: TOKI listens for exactly
  as long as the key is physically held — a pause mid-sentence while still
  holding does **not** end the recording early, and releasing the key ends
  it immediately rather than waiting out the silence hangover. The
  hold-vs-tap decision is made from how long the key was actually down
  (`HOLD_TO_TALK_MS` in `toki_desktop_mark.py`, currently 350 ms) — a normal
  tap never crosses that, so tap behavior is completely unchanged.
- **Stop pressing + silence for ~1.8 s** (tap mode only): recording ends,
  faster-whisper transcribes, command fires through the orchestrator, mark
  returns to idle notch.

### Active / Working
While the orchestrator is running the command, mood → `energetic` (red rings).

- **Task-based command** (create a folder, take a screenshot, rename a file,
  ...): mark shows a brief **Done** pill, then shrinks back to idle. It only
  ever says "Done" for these — never for something that actually has an
  answer to show.
- **Info-based command** (how many files are in this folder, what's my disk
  usage, read this file, ...): the mark transitions into a fixed-size,
  rounded, scrollable card showing the real answer — reformatted into a
  readable bulleted paragraph rather than PowerShell's raw fixed-width table
  output (see `display_strategy.py`'s `_prettify_powershell_output()`) where
  that's possible. This card is **sticky**: it does not auto-collapse on its
  own. It stays up until you click anywhere else on the screen.

---

## Behavior details

| Situation | What happens |
|---|---|
| Say nothing after Ctrl+K | 6 s timeout → no-speech, mark goes idle |
| Speak, pause, tap Ctrl+K again | Silence timer resets, keeps listening |
| Hold Ctrl+K, pause mid-sentence, keep holding | Recording keeps going — the hold itself is the "keep listening" signal, not silence detection |
| Release Ctrl+K after a genuine hold | Recording ends immediately, no hangover wait |
| Ctrl+K while working | Does nothing (session guards against double-trigger) |
| Task command finishes | "Done" pill, auto-fades, mark returns to idle |
| Info command finishes | Persistent scrollable card, stays open until you click elsewhere |
| Orchestrator unavailable | Transcription prints to stdout, mark still works |
| sounddevice / pynput missing | `unavailable` signal fires, error in stdout, widget stays up |

---

## Conversational context / slot memory

TOKI keeps a small amount of session-only context so an obvious follow-up
doesn't need to be spelled out again:

- **`orchestrator._last_touched`** — the path TOKI itself most recently
  created, renamed, moved, copied, generated, or (as of this change)
  screenshotted. This is what "it"/"that" resolve against in a follow-up
  like "now delete it" or "put it in function" — see
  `resolve_anaphoric_target()` and the newer
  `resolve_move_or_copy_with_context()`, both in `extractor.py`.
- **`orchestrator._recent_folder_names`** — a small name → path map, capped
  at the 3 most recently mentioned folders, of places TOKI has made or
  moved/copied something into this session. So "make a folder called
  Homework" then later "put it in Homework" reuses the same folder instead
  of creating a duplicate; a brand-new bare name ("put it in Function") gets
  created fresh, safely (never treated as a rename-via-move target).

This is intentionally small and short-lived — the last few things you were
just doing, not a growing whole-session memory — so it can't accidentally
resolve a reference against something from an unrelated, long-forgotten part
of the conversation.

---

## Wiring into orchestrator

`main_widget.py` does this automatically if your `orchestrator.py` is in the
same folder.  If it imports cleanly, speech goes through
`orchestrator.process_request()` just like a typed message.  If it doesn't import,
the widget still runs — transcriptions just print to stdout.

To wire the scheduler manually:

```python
from toki_desktop_mark import DesktopMark
mark = DesktopMark()
mark.set_scheduler(orchestrator.scheduler)  # hover panel reads from here
mark.show()
```
