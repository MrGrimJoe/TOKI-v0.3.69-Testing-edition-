# TESTING_LOG.md — systematic pass, classification/extraction layer

> **Point-in-time log, not a live document:** written when TOKI had 64
> intents total; it has 80 now (see README.md). Treat the specific
> pass/fail claims below as accurate for the version they were tested
> against, not as current fact — check STATUS.md's recent entries or
> re-run the relevant test for anything that matters to you today.

Purpose: work through every intent TOKI has (64 total, minus app_control's
6 which need real Windows UI) and document, honestly, what's verified
working, what's a real bug (fixed or not), and what needs YOUR machine
because this sandbox can't check it. Kept separate from STATUS.md so that
file doesn't keep growing — this is the working log for this specific pass.

**Environment reminder:** this sandbox is Linux, no Ollama, no real
Windows. Everything below is either (a) classification/slot-extraction
logic, fully verifiable here with no dependencies, or (b) explicitly
marked as needing your machine. Nothing here is guessed.

---

## A methodology mistake I made and want to be upfront about

My first sweep of the 47 named `powershell`-kind intents showed 22
mismatches. On investigation, **15 of those 22 were my own test-script bug**,
not TOKI's: I reused one `WindowsAIAssistant` instance across all 47 test
prompts in a loop, and once an early ambiguous prompt set `self._pending`,
every later prompt in the loop got silently routed through
`_resume_pending()`'s "I still didn't catch that" fallback instead of fresh
classification — regardless of what that later prompt actually was. Redid
the whole sweep with a fresh instance per prompt and the real number of
mismatches dropped to **7**. Flagging this so the 22-vs-7 discrepancy
doesn't look like inconsistent reporting — it's a corrected methodology,
not a moving target.

---

## Real bugs found and FIXED this session (verified, tests added)

### 1. `_extract_city()` required a capital letter — lowercase cities silently failed
**Found via:** `whats the weather in lahore` → fell back to "couldn't determine
your location" even though a city was explicitly named.
**Root cause:** `_CITY_RE` was `\bin\s+([A-Z][a-zA-Z\s]+?)...` — required the
match to start with an uppercase letter. Never caught before because the
only existing tests always used "Lahore"/"Karachi", properly capitalized.
**Fix:** case-insensitive match, plus trailing-filler stripping ("please",
"right now", etc.) that a capital-letter-free match would otherwise swallow.
**Tests:** `tests/test_extractor.py::TestCityExtractionCaseInsensitive` (7 cases).
**Affects:** GET_WEATHER, GET_FORECAST (both use the same `_extract_city`).

### 2. `FIND_FILES_BY_CONTENT` only recognized 3 exact trigger phrases
**Found via:** `search inside files in downloads for TODO`,
`find files that contain TODO`, `search files for the word urgent`, and
`search for TODO in my files` all returned `None` — only "containing X" /
"with the text X" / "for the text X" worked.
**Root cause:** narrow regex, no coverage for the many natural ways to ask
this.
**Fix:** broader trigger (search/find/look ... for/containing/contains/with)
plus post-processing to strip leading "the word/text/phrase" filler and
trailing "in my files"/"in downloads" location filler. Note: tried baking
"for the word" as its own alternative directly into the trigger regex first
— that failed because `re.search()` always prefers the earliest starting
match position in the string, so "search ... for" (starting earlier) beat
a more specific "for the word" alternative starting later, regardless of
alternation order. Switched to post-processing instead of fighting that.
**Tests:** `tests/test_extractor.py::TestFindFilesByContentPhrasing` (10 cases,
including 2 negative cases confirming a bare trigger with nothing after it
still correctly returns None).

---

## Real bugs found, NOT fixed — need deliberate graph-retraining work, not a quick patch

These are classification-layer (graph_router.py / kuzu graph), not
extraction-layer. I stopped short of patching them myself because the fix
isn't a regex tweak — it's rebalancing TF-IDF training data across
intents that currently compete for the same content words, and doing that
blind risks quietly breaking other things that currently classify
correctly. Flagging clearly rather than guessing at a fix.

### 3. `"kill chrome"` / `"stop chrome"` / `"close chrome"` / `"terminate chrome"` all fail
**Real cause, confirmed directly:** the graph's best match for `"kill chrome"`
is actually **`LAUNCH_APP`** at confidence 0.203 (below the 0.4 threshold,
so it correctly returns None rather than wrongly launching Chrome) — not
`KILL_PROCESS`. "chrome" is such a strong signal for LAUNCH_APP (since so
many phrasings are "open/launch chrome") that it drags the match away from
KILL_PROCESS even when paired with "kill".
**What DOES work:** `"kill process chrome"`, `"kill the chrome process"` — as
soon as the literal word "process" is present, confidence clears the
threshold and KILL_PROCESS matches correctly.
**Practical impact:** a very natural, extremely common phrasing ("kill
chrome", "stop chrome") currently does nothing but ask for clarification
instead of dispatching. Worth prioritizing, since this is probably a
top-5-most-common real-world phrasing for this intent.

### 4. `"read report.txt"` fails; `"show contents of report.txt"` mis-fires to GET_CLIPBOARD
**Real cause, confirmed directly:** `"read report.txt"` DOES correctly
best-match READ_FILE, but at confidence 0.357 — just under the 0.4
threshold. `"read the file report.txt"` and `"read file report.txt"` (more
content words) both work fine.
**New finding, not previously known:** `"show contents of report.txt"`
confidently mis-fires to **GET_CLIPBOARD**, not READ_FILE — a genuinely
wrong classification (not a threshold near-miss), presumably because "show"
+ "contents" overlaps more with the clipboard intent's phrasing bank.

### 5. `"find files named report"` confidently mis-fires to FIND_DUPLICATE_FILES
**Real cause, confirmed directly:** this ISN'T a near-miss — confidence is
0.588, comfortably above threshold, just pointed at the wrong intent.
`"find files called report"` and `"find a file named report"` both work
correctly and hit FIND_FILES. `"search for files named report"` mis-fires
to yet a THIRD intent, FIND_FILES_BY_CONTENT.
**Practical impact:** whether "named"/"called" is used, and whether "find"
or "search for" leads, changes which of 3 different intents gets hit for
what should be one consistent request. This one is probably the most
concerning of the three, since it's confidently wrong rather than
correctly declining.

**Recommended next step for these 3:** look at how many phrasing examples
each of KILL_PROCESS / READ_FILE / FIND_FILES has in the graph's training
data relative to the intents they're losing to (LAUNCH_APP, GET_CLIPBOARD,
FIND_DUPLICATE_FILES, FIND_FILES_BY_CONTENT) — my guess, not yet verified,
is those competing intents simply have denser/more varied phrasing banks.
Adding more natural phrasing examples for the losing intents is probably
the right fix, but that's a data change, not a code change, and deserves
your own review before I touch the graph's source phrasing data.

---

## Confirmed WORKING (verified fresh-instance, no false positives)

Straight commands, correctly classified end-to-end through
`WindowsAIAssistant.process_request()`:

COPY_ITEM, COUNT_FILES, COUNT_FOLDERS, DELETE_ITEM, DISK_USAGE,
EXPORT_FOLDER_LISTING_CSV, FIND_DUPLICATE_FILES, FIND_PROCESS,
FIND_SERVICE, GET_CLIPBOARD, HOSTNAME, ITEM_PROPERTIES, LIST_FILES,
LIST_PRINTERS, LIST_USB_DEVICES, LOCK_WORKSTATION, MAKE_FILE, MAKE_FOLDER,
MOVE_ITEM, NETWORK_INFO, OPEN_TASK_MANAGER, PATH_EXISTS, PROCESS_LIST,
RENAME_ITEM, RESOLVE_PATH, SET_CLIPBOARD, SYSTEM_INFO, SYSTEM_LOCALE,
SYSTEM_UPTIME, TAKE_SCREENSHOT, TEMPERATURE_SENSORS, TOGGLE_MUTE,
TOP_PROCESSES_BY_CPU, VOLUME_DOWN, VOLUME_UP, WAIT_FOR_PROCESS,
BATTERY_STATUS, CURRENT_LOCATION, CURRENT_USER, EMPTY_RECYCLE_BIN,
OPEN_ITEM (graph-level; app-resolution needs real Windows, see below),
SPLIT_PATH, SCHEDULE_COMMAND, CANCEL_SCHEDULED, CONDITIONAL_COMMAND (all
three from the previous session, reconfirmed still passing).

**Note on SPLIT_PATH:** my first pass showed this as a "mismatch" using
`C:\Users\test\file.txt` — that's not a bug, it's the sandbox correctly
REFUSING a path outside its allowed roots (`D:\` and the Desktop folder).
Retested with a valid sandboxed path and it worked correctly. Filing this
so it's clear that one was my test data being wrong, not TOKI.

---

## Cannot verify from this sandbox — needs your machine

### Execution-level (all `powershell`-kind intents, 47+1160/1220 graph ones)
Classification and slot-extraction are proven correct above. The actual
PowerShell call itself (`RunningCommand` in executor.py) has never
actually run on a real Windows box during this whole review — this
sandbox is Linux. **Please run a batch of these for real** and confirm
the PowerShell actually executes and returns sensible output, not just
that TOKI picked the right intent.

### `api`-kind intents needing live network (GET_WEATHER, GET_FORECAST, SEARCH_WEB)
Slot extraction confirmed correct (including the city-name fix above).
Actual weather API and DuckDuckGo/Wikipedia calls can't be verified here —
this sandbox has no route to those domains. Please run these for real:
```
whats the weather in lahore
give me a 5 day forecast for karachi
search the web for best laptops 2026
```

### The scheduling/conditional fire path, for real
Previous session confirmed the classify → dispatch → fire pipeline is
logically correct (verified via history inspection), but the actual
PowerShell command that fires after a delay, and the actual
`Get-CimInstance -ClassName Win32_Battery` call the condition-poller uses,
were never run on real Windows. Please run:
```
show me disk usage in 10 seconds
[wait 10+ seconds, confirm it actually ran]

if battery is low, launch notepad
if battery is low, launch notepad          <- restate as the follow-up answer
[unplug charger or wait for a natural low-battery moment, confirm it fires]
```

### `app_control` (LAUNCH_APP resolution, CLICK_ELEMENT, TYPE_INTO_ELEMENT, etc.)
Needs pywinauto + real Windows UI — completely out of scope for this
sandbox, as already known. Also worth noting: OPEN_ITEM/LAUNCH_APP
classify correctly at the graph level here, but app/file RESOLUTION
(deciding if "notepad" is an installed app vs. a file) needs the real
Windows app registry and filesystem, so even "working" graph classification
doesn't guarantee the full command succeeds — please test this directly:
```
open notepad
open chrome
launch calculator
open my resume.docx
```

---

## Suite state as of this log
`pytest tests/` → **304 passed, 3 xfailed**, stable. Up from 232 at the
start of this whole review (55 scheduling/conditional tests +
7 city-extraction tests + 10 find-files-by-content tests = 72 new tests
total across both sessions).

---

## SESSION 3 — real Windows run, real Ollama, real bugs found (project owner ran this)

The project owner ran the actual test suite and 5 `batch_test_live.py`
prompt files on real Windows with a real Ollama model (phi4-mini). This
is qualitatively different data from anything in sessions 1-2 — first
time this codebase has been exercised for real. Findings below.

### Bug found and FIXED: pytest suite broke on Windows (21 errors) — my own regression
**What happened:** `python -m pytest tests/ -v` on Windows produced 21
`RuntimeError: Could not set lock on file : ...\toki_graph_db` errors, all
in `test_chain_split_viability.py`, plus 1 genuine test failure
(`test_scheduled_command_actually_fires_and_redispatches`, `assert 2 > 2`).
**Root cause, confirmed:** `test_scheduling_and_conditionals.py` (added in
session 2) creates 14 `WindowsAIAssistant()` instances across its tests,
none of which ever called `.shutdown()` — each one opens its own
`GraphRouter` on the same `toki_graph_db` file and never releases it. On
Linux (this sandbox) that went unnoticed; kuzu's file locking is
apparently more permissive there. On real Windows, kuzu enforces the lock
strictly, so `test_chain_split_viability.py` (a completely unrelated,
pre-existing test file that also opens its own `GraphRouter` on the same
path) failed to acquire the lock, 21 times over.
**Fix:** added a `assistant` pytest fixture with `yield` + teardown that
calls `.shutdown()` unconditionally, even if the test body raises
partway through (which a manual "call shutdown() at the end of the test"
convention does not cover). Replaced all 14 raw instantiations with it.
**Also fixed:** the one genuine failure. Root cause: the test slept a
fixed 1.8s then asserted once; on real hardware, firing a scheduled
command spawns a real PowerShell subprocess (RunningCommand), which can
easily take longer than a short fixed sleep, especially on the first
PowerShell call in a process (interpreter startup cost this sandbox's
Linux-based timing never had to account for). Fixed by polling for up to
10s instead of sleeping once for a fixed window.
**Verified:** both fixes confirmed in this sandbox; suite still 304/3.
Windows re-run needed to confirm the lock errors are actually gone there
too — sandbox can't reproduce kuzu's stricter Windows locking behavior to
verify this directly, only reason about the fix.

### Bug found, NOT yet fixed — Tier A intents silently shadow destructive Tier B commands
**This is the most serious finding across both sessions.** Confirmed
directly, not just observed in the log:

```
wipe disk 2                  -> DISK_USAGE            (should be WCL_Clear-Disk, destructive)
bitlocker lock mount point D -> LOCK_WORKSTATION       (should be WCL_Lock-BitLocker, destructive)
disable dedup volume on E    -> VOLUME_UP              (should be WCL_Disable-DedupVolume, destructive)
```

**Root cause, fully traced:** `graph_router.py`'s own docstring documents,
correctly, that Tier B (the ~1160/1220 broader Windows command library)
is deliberately excluded from graph dispatch — TOKI's executor doesn't
yet know how to run raw WCL syntax, so a Tier B match is treated as a
miss and falls through to the LLM+WCL-resolver path instead (confirmed:
`WCL_Get-VM`/`WCL_Clear-Host` in the live log both took ~18-20s,
consistent with a real Ollama call, not the near-instant graph path).
**That part is working as designed.** The actual bug: Tier A and Tier B
are scored in *separate, non-competing* pools (also intentional, to stop
Tier B's larger pool from drowning out correct Tier A matches — see
graph_router.py's own history of that exact prior bug). But this means
when a query's content words genuinely belong to a Tier B command
(`"wipe disk"` IS a real phrasing for `Clear-Disk`, confirmed directly
against the live kuzu graph — 6 phrasing nodes exist for it, including
`'wipe disk'` verbatim), Tier B never gets a chance to be the answer —
the graph doesn't know "the right answer is Tier B, so return a miss
and let the LLM handle it." It only knows "score every Tier A candidate,"
and whatever Tier A command shares ANY keyword (here: "disk", "lock",
"volume") wins outright once it clears the 0.4 confidence threshold —
even though it's the wrong answer and a real, better, correctly-flagged
`destructive` command exists one tier over.
**Confirmed the danger levels are real, not assumed:** checked the source
JSON directly — `Disable-DedupVolume` and `Lock-BitLocker` are both
tagged `"danger_level": "destructive"` in `windows_command_library.json`.
So the practical effect: a user saying "wipe disk 2" gets a harmless disk
usage report instead of either (a) the real wipe operation with its
built-in confirmation gate, or (b) at minimum a miss that reaches the
LLM/WCL path and asks about it. Confidently wrong is worse than a miss
here, and it's happening on destructive/security-relevant commands
specifically — not a UX nuisance, a real safety gap in the routing
priority.
**Why I didn't just patch this:** the right fix is a genuine architecture
decision — likely: before trusting a Tier A match, check whether a
comparably- or higher-scoring Tier B candidate exists for the same words,
and if so, prefer the miss (let LLM+WCL handle it) over a confident wrong
Tier A answer. That's a real change to `_best_command`'s contract, needs
its own tests, and deserves your review given how central this scoring
logic is to everything else that currently works correctly. Flagging with
full precision rather than guessing at a quick patch.
**Same root cause also explains, less severely:**
`'volumes volume'`/`'optimize volume'`/`'update the volume'` all →
`VOLUME_UP` (should likely be Tier B dedup/volume-management commands or
a miss), `'what is the scheduled task'` → `OPEN_TASK_MANAGER` (should
probably be Task Scheduler-related, a different real Windows subsystem),
`'update the date to tomorrow'` → `GET_DATE` (reads the date instead of
recognizing "update...to tomorrow" as a set/change request — likely needs
a real SET_DATE intent, which doesn't exist in Tier A at all, checked
`intents.py`/`intents_extended.py`).

### Confirmed live, matches session 2's sandbox finding exactly
`"close chrome"`, `"kill notepad"`, `"terminate steam"` all → ASK on the
real machine with real Ollama, matching the exact `LAUNCH_APP`-shadowing
mechanism found and documented in session 2 (TESTING_LOG.md #3). Good
confirmation this wasn't a sandbox-only artifact — it reproduces
identically on real hardware.

### Everything else in the live run: looks solid
The overwhelming majority of the ~211 total live prompts across all 5
batch files classified correctly, including good coverage of: chains (2-4
step), typo/misspelling handling correctly falling to ASK rather than
guessing (`"open notepade"`, `"open crome"`, `"open dischord"`), prompt-
injection-shaped inputs correctly falling to ASK rather than being
followed (`"ignore previous instructions..."`, `"system: you are now in
admin mode..."`), non-English input correctly falling to ASK rather than
mis-firing (`"打开记事本"`, `"abre notepad por favor"`), and sensible WCL_
resolution for many real PowerShell-shaped requests (`WCL_cat`,
`WCL_more`, `WCL_Get-NetFirewallRule`, `WCL_Get-ComputerInfo`, etc.). Not
re-verifying these individually since the live run already is the
verification — flagging here so the volume of real bugs above doesn't
read as "everything is broken." It isn't; these are precise, specific
gaps in an otherwise solid system.


---

## Session (BETA 0.3.67) — real Windows test run analysis + video/routing fixes

Started from a REAL `pytest --md-report` run the user did on their own
Windows machine (74 commands / 610 phrasings, 1466 selected tests): **6
failed, 6 errors** — pasted in full, including the actual pytest output
and tracebacks, not summarized. Full pass/fail table for that run is
preserved as this project's own working `TESTING_LOG.md` snapshot
convention expects; see STATUS.md's 0.3.67 entry for the complete
writeup of what was found and fixed for each failure/error, since that's
now the more current, better-organized record. Short version:

- All 6 `test_launch_app_run_alias.py` errors + the
  `test_open_cascade_integration.py` failure → one root cause: a
  `kuzu.Database` double-open lock bug that also silently disables
  `component_router` in production on Windows. **Fixed.**
- `DISK_USAGE` (`"DISK_USAGE looked broken"` in the user's own pytest
  output) + `NETWORK_INFO` → invalid PowerShell from a stale `{{`/`}}`
  escaping habit on commands that skip `.format()`. **Fixed**, plus a
  new regression test sweeping every other zero-slot PowerShell intent
  for the same mistake.
- 3 `test_document_backend.py` pandoc failures — confirmed
  environment-only (pandoc genuinely isn't on the user's PATH either,
  same as this sandbox); not a code bug.
- `test_start_then_stop_dictation` — Windows-UI-dependent
  (`requires_windows`), not investigated this session; flagged in
  STATUS.md's "still open" section rather than silently dropped.

Then, from live chat feedback (not the pytest run): a reported ffmpeg
over-blocking bug in the video downloader, a reported routing gap
("its only currently routing to web search due to a few gaps in my
vocab") specifically around downloading videos, and a reported dozen
real Chrome tabs left open after an unattended test run. All three
investigated and fixed/mitigated — see STATUS.md's 0.3.67 entry for the
full writeup; new/changed test files: `tests/test_video_downloader.py`,
`tests/test_apis.py`, `tests/test_video_download_routing.py` (new),
`tests/execution/test_live_dispatch.py` (one test marked `disruptive`).

**Full local sandbox re-run after all fixes above** (Linux, xvfb, not a
substitute for the real Windows run this session started from):

```
1432 passed, 66 skipped, 1 xpassed, 4 failed in ~75s
```

The 4 failures are the same pre-existing environment-only gaps called
out above and in STATUS.md (pandoc not installed; one test hard-requires
a real Windows filesystem for backslash-path verification) — not new,
not caused by anything in this session.

**Not independently re-verified against a fresh table on the user's own
Windows machine yet** — that's the next real check, same "actually run
it" standard the rest of this file holds itself to. This entry is honest
about that: everything above is sandbox-confirmed plus direct code
reading of the actual failure that occurred on real hardware, not
re-confirmed end-to-end on Windows by this session.

---

## Session (BETA 0.3.68) — broad routing-generalization sweep, all 74 Tier A intents

Direct continuation of the 0.3.67 session above, prompted by a plain
question: "how much longer is this gonna take." One feature's worth of
routing fixes (video download) isn't enough data to answer that
honestly, so this session ran the same kind of sweep across everything.

**Method:** 2-3 natural paraphrases per intent (153 total), written
without looking at the actual phrasing bank first, run against the live
GraphRouter. **Result: 68% hit rate, 6 intents at a zero-hit rate.**
Diagnosed with `audit_tier_a.py`'s own scoring internals (not guessed):
5 of the 6 zero-hit intents were already ranking correctly at #1, just
under the confidence threshold, because the paraphrase used a concrete
noun ("chrome", "spotify", "pc") their phrasing banks never included.
Added targeted phrasings, rebuilt the graph, re-swept: **74.5% hit
rate**, zero-hit intents down to 1 (a genuine three-way semantic overlap
between GROUP_FILES_BY_EXTENSION/SORT_FOLDER_BY_TYPE/
ORGANIZE_FILES_BY_TOPIC, left as a tracked gap rather than risking a
regression on either neighbor).

Committed the sweep as `tests/test_routing_generalization_sweep.py` --
101 confirmed hits (regression guard) + 38 tracked known gaps
(`xfail(strict=True)`, each with its specific reason, promoted to a
confirmed hit the moment one gets fixed for real). Also added
`tests/test_component_router_health.py`, a direct regression guard for
the 0.3.67 kuzu double-Database fix (asserts a real
`WindowsAIAssistant()` actually gets a live, correctly-shared
component_router, not just "didn't crash this time").

**Full local sandbox run:** 1536 passed, 66 skipped, 1 xpassed, 38
xfailed (expected), 4 failed (same pre-existing environment-only gaps).

See STATUS.md's 0.3.68 entry for the complete phrasing-level writeup.
This is meant to be re-run on the real Windows machine and re-run again
after any future phrasing changes -- the honest, current picture of
Tier A's natural-language coverage as a whole, not just the one intent
that happened to get complained about.

---

## BETA 0.3.69 — closing the 38 tracked known gaps, two normalize() bugs,
one caught-before-shipping regression

Direct continuation of the sweep above. Went through the 38 `KNOWN_GAPS`
one at a time with the same "is the router already ranking this correctly,
just under threshold?" check, using a standalone script against the live
`GraphRouter` (not just eyeballing the phrasing bank).

**Found via that process, not guessed:** `normalize()` (duplicated in
`graph_router.py` and `migrate_to_kuzu.py`) turned apostrophes into a
space, splitting `"what's"` into `"what"` + a spurious `"s"` token instead
of collapsing it to `"whats"` — the spelling most of the corpus already
uses. Confirmed 70+ apostrophe/no-apostrophe inconsistencies for the same
words across `tier_a_phrasings.py`. Fixed in both files (must match
exactly, since `migrate_to_kuzu.py` stores pre-normalized `Phrasing.text`
that `graph_router.py` re-reads at query time). This is a normalize()-
level fix, not a per-phrasing patch, and closed `NETWORK_INFO`'s gap for
free.

While rebuilding after that fix, a second, separate bug surfaced:
`migrate_to_kuzu.py`'s `normalize()` never had the `.txt`/`.exe` suffix-
stripping `graph_router.py`'s has, despite its own docstring claiming
otherwise. `audit_tier_a.py` caught it immediately as a self-consistency
failure on `"convert draft.txt to markdown"`. Fixed by adding the missing
`_STRIPPED_SUFFIXES` list to `migrate_to_kuzu.py`.

**Closed 19 of 38 gaps** with one targeted, verbatim phrasing each
(full list in STATUS.md's 0.3.69 entry). Each one verified directly
against the live `GraphRouter` after rebuilding, then moved from
`KNOWN_GAPS` to `HIT_EXPECTED` in the test file.

**Two fixes were tried and reverted after the full suite (not
`audit_tier_a.py`) caught real regressions:**
- `FIND_FILES_BY_CONTENT` — the new phrasing diluted the intent's own
  vector enough to drop a different, previously-passing phrasing below
  threshold. `audit_tier_a.py` caught this one on its own.
- `TOGGLE_MUTE`/`VOLUME_DOWN`/`VOLUME_UP` — three additions that each
  looked zero-cost individually (identical content-word sets to existing
  phrasings, stopwords aside) collectively broke all 6 cases of
  `TestVolumeOffMeansMute` in `test_graph_router.py`, a carefully-tuned
  fix from 0.3.49 for "volume off must never mean volume up." This one
  only showed up on the full suite run — `audit_tier_a.py` only checks
  one intent's own phrasings against each other, and can't see a
  regression that crosses into a different test file entirely. This is
  the reason the full suite has to run after every phrasing change here,
  not just the sweep file or the audit script.

**Full local sandbox run, final state this session:** 1563 passed
(up from 1544 at the start), 66 skipped, 3 deselected, 20 xfailed
(expected), 4 failed (same pre-existing environment-only gaps as every
prior session — pandoc/LaTeX missing, 3 tests requiring a real Windows
filesystem), 0 unexpected failures, 0 unexpected passes.

See STATUS.md's 0.3.69 entry for the complete phrasing-level writeup and
the full reasoning behind both reverted attempts.
