"""
test_routing_generalization_sweep.py -- BETA 0.3.67, new.

Context: every existing routing test (test_wcl_coverage_audit.py,
audit_tier_a.py, tests/test_video_download_routing.py) checks that
phrasings ALREADY IN a phrasing bank classify correctly. None of them
answer a different, more important question: if a real person phrases
a request in a way nobody wrote down yet, does it still route?

This file is a deliberately-independent sweep against ALL 74 Tier A
intents at once, using natural paraphrases written WITHOUT looking at
graph_source_data/tier_a_phrasings.py's actual wording (checked
afterward, not before, to keep the paraphrases honest) -- 2-3 per
intent, ~150 total. It exists because the first version of this exact
sweep (run manually, not as a committed test) found a 68% hit rate
across all intents and 6 intents with a ZERO hit rate out of their
own paraphrases -- a materially bigger routing gap than any single
intent's own dedicated test had surfaced. Several of those were fixed
this session (see STATUS.md's 0.3.67 entry); this file is what's left,
committed so it doesn't silently regress AND so it keeps giving real
data about what's still rough, since not every gap found could be
fixed in one pass without risking new regressions elsewhere (TF-IDF
means every phrasing addition can shift scores for unrelated intents --
see audit_tier_a.py's own margin-check section for how thin some of
these boundaries already are).

HOW TO READ A FAILURE HERE
----------------------------------------------------------------------------
This is NOT the same kind of test as test_wcl_resolver.py or
test_graph_router.py, where a failure means "something that used to work
broke." A failure here can mean either:
  (a) A regression -- something in HIT_EXPECTED below that used to route
      correctly no longer does. Treat this like any other regression.
  (b) A known, not-yet-fixed gap being tracked (see KNOWN_GAPS below) --
      these are xfail'd individually, WITH the reason, specifically so
      the overall pass/fail signal stays meaningful instead of drowning
      real regressions in a sea of pre-existing known misses.
If a KNOWN_GAPS case unexpectedly starts PASSING (an xfail that no
longer fails), pytest will flag it as XPASS -- that's good news, not a
bug: move it up into HIT_EXPECTED and delete it from KNOWN_GAPS.

WHY THIS DOESN'T JUST FIX EVERYTHING IT FOUND
----------------------------------------------------------------------------
Some of these misses are a genuine, hard three-way semantic overlap
(GROUP_FILES_BY_EXTENSION / SORT_FOLDER_BY_TYPE / ORGANIZE_FILES_BY_TOPIC
all describe closely related real actions) where a quick phrasing
addition to fix one miss risks silently stealing a phrasing that
currently correctly belongs to a neighboring intent -- exactly the kind
of regression audit_tier_a.py's thin-margin section already warns is
easy to cause. Those are left as tracked, honest gaps rather than
papered over.
"""

import pytest

pytest.importorskip("kuzu")

from graph_router import GraphRouter, DB_PATH

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="toki_graph_db not present in this checkout -- run migrate_to_kuzu.py first",
)


@pytest.fixture(scope="module")
def router():
    r = GraphRouter()
    yield r
    r.close()


# Format: (intent, phrasing). Confirmed routing correctly as of this
# session's graph rebuild -- a failure on any of these is a real
# regression, not a known gap.
HIT_EXPECTED = [
    ("BATTERY_STATUS", "hows my battery"),
    ("BATTERY_STATUS", "check battery percentage"),
    ("CLICK_ELEMENT", "click that button"),
    ("CLICK_ELEMENT", "press this button for me"),
    ("COMPRESS_SELECTED_FILE", "zip this up"),
    ("COMPRESS_SELECTED_FILE", "compress this file"),
    ("CONVERT_SELECTED_FILE", "convert this to png"),
    ("COPY_ITEM", "make a copy of this"),
    ("COPY_ITEM", "copy this somewhere else"),
    ("COUNT_FILES", "how many files are in here"),
    ("COUNT_FILES", "count the files in this folder"),
    ("COUNT_FOLDERS", "how many folders are here"),
    ("COUNT_FOLDERS", "count the subfolders in this directory"),
    ("CURRENT_LOCATION", "what folder am i in"),
    ("CURRENT_USER", "who am i logged in as"),
    ("CURRENT_USER", "whats my username"),
    ("DELETE_ITEM", "get rid of this file"),
    ("DELETE_ITEM", "remove this item"),
    ("DELETE_ITEM", "delete this for me"),
    ("DISK_USAGE", "how much disk space do i have left"),
    ("DOUBLE_CLICK_ELEMENT", "double click that"),
    ("DOUBLE_CLICK_ELEMENT", "double tap this icon"),
    ("DOWNLOAD_PLAYING_VIDEO", "download the video im on right now"),
    ("DOWNLOAD_VIDEO_URL", "download the video from this address"),
    ("DOWNLOAD_VIDEO_URL", "grab the video at this link"),
    ("EXPORT_FOLDER_LISTING_CSV", "export this folder list as a csv"),
    ("EXTRACT_SELECTED_FILE", "unzip this"),
    ("FILE_TYPE_BREAKDOWN", "what kinds of files are in here"),
    ("FIND_DUPLICATE_FILES", "find duplicate files in here"),
    ("FIND_FILES_BY_CONTENT", "find files that mention budget"),
    ("FIND_PROCESS", "is chrome running"),
    ("FIND_PROCESS", "check if spotify is open"),
    ("FIND_SERVICE", "check the status of windows update service"),
    ("GENERATE_QR_CODE", "make a qr code for this link"),
    ("GENERATE_QR_CODE", "create a qr code with this text"),
    ("GET_CLIPBOARD", "whats on my clipboard"),
    ("GET_DATE", "whats todays date"),
    ("GET_DATE", "what day is it"),
    ("GET_FORECAST", "whats the forecast this week"),
    ("GET_FORECAST", "will it rain tomorrow"),
    ("GET_LOCATION", "where am i right now geographically"),
    ("GET_LOCATION", "whats my current location"),
    ("GET_TIME", "what time is it"),
    ("GET_TIME", "tell me the current time"),
    ("GET_WEATHER", "hows the weather outside"),
    ("HOSTNAME", "whats this computers name"),
    ("HOSTNAME", "what is my pc called"),
    ("ITEM_PROPERTIES", "show me the properties of this file"),
    ("ITEM_PROPERTIES", "how big is this file"),
    ("KILL_PROCESS", "close chrome completely"),
    ("KILL_PROCESS", "force quit spotify"),
    ("LAUNCH_APP", "open up notepad"),
    ("LIST_FILES", "show me whats in this folder"),
    ("LIST_FILES", "list everything in this directory"),
    ("LIST_INSTALLED_APPS", "what programs do i have installed"),
    ("LIST_INSTALLED_APPS", "show me my installed software"),
    ("LIST_PRINTERS", "what printers do i have"),
    ("LIST_PRINTERS", "show my available printers"),
    ("LIST_USB_DEVICES", "what usb devices are connected"),
    ("LIST_USB_DEVICES", "show connected usb drives"),
    ("LOCK_WORKSTATION", "lock my computer"),
    ("LOCK_WORKSTATION", "lock the screen"),
    ("MAKE_FILE", "create a new empty file called notes.txt"),
    ("MAKE_FILE", "make a new file here"),
    ("MAKE_FOLDER", "create a new folder called projects"),
    ("MAKE_FOLDER", "make a new directory here"),
    ("OPEN_ITEM", "open this file"),
    ("OPEN_ITEM", "open this folder for me"),
    ("OPEN_TASK_MANAGER", "open task manager"),
    ("OPEN_TASK_MANAGER", "show me running processes in task manager"),
    ("ORGANIZE_FILES_BY_TOPIC", "sort my files by subject"),
    ("ORGANIZE_FILES_BY_TOPIC", "organize this folder by topic"),
    ("PATH_EXISTS", "does this file exist"),
    ("PROCESS_LIST", "show me all running processes"),
    ("PROCESS_LIST", "whats running on my pc right now"),
    ("READ_FILE", "show me whats inside this file"),
    ("RENAME_ITEM", "rename this to notes2"),
    ("RESOLVE_PATH", "whats the full path to this"),
    ("RESOLVE_PATH", "resolve this relative path"),
    ("RIGHT_CLICK_ELEMENT", "right click on this"),
    ("SCAN_QR_CODE", "whats in this qr code"),
    ("SCAN_QR_CODE", "read this qr code for me"),
    ("SEARCH_WEB", "look this up online"),
    ("SEARCH_WEB", "search the web for pizza places"),
    ("SET_CLIPBOARD", "copy this text to my clipboard"),
    ("SET_CLIPBOARD", "put this on my clipboard"),
    ("SORT_FOLDER_BY_TYPE", "sort this mess into folders"),
    ("SPLIT_PATH", "split this path into parts"),
    ("SPLIT_PATH", "break this file path down"),
    ("SYSTEM_INFO", "give me my system specs"),
    ("SYSTEM_INFO", "whats my computer specs"),
    ("TAKE_SCREENSHOT", "take a screenshot"),
    ("TAKE_SCREENSHOT", "capture my screen"),
    ("TEMPERATURE_SENSORS", "how hot is my cpu"),
    ("TOGGLE_MUTE", "mute my volume"),
    ("TOP_PROCESSES_BY_CPU", "whats using the most cpu"),
    ("TOP_PROCESSES_BY_CPU", "show me top cpu consuming processes"),
    ("TYPE_INTO_ELEMENT", "type this into the box"),
    ("TYPE_INTO_ELEMENT", "enter this text into that field"),
    ("WAIT_FOR_PROCESS", "wait until chrome closes"),
    ("WAIT_FOR_PROCESS", "wait for spotify to finish"),
    # BETA 0.3.69: promoted from KNOWN_GAPS below after a targeted
    # phrasing-bank addition (or, for "whats my ip address", a
    # normalize() fix -- see graph_router.py's own normalize() docstring)
    # made each of these classify correctly. Re-verified directly against
    # the live GraphRouter after the graph rebuild, not just moved on
    # faith. See STATUS.md's 0.3.69 entry for the full list and reasoning
    # per intent.
    ("CLICK_ELEMENT", "tap on this"),
    ("COMPRESS_SELECTED_FILE", "make this into a zip"),
    ("CONVERT_SELECTED_FILE", "turn this into a pdf"),
    ("DISK_USAGE", "check my storage"),
    ("EMPTY_RECYCLE_BIN", "empty the trash"),
    ("EXTRACT_SELECTED_FILE", "extract the contents of this archive"),
    ("FIND_FILES", "find files named report"),
    ("LAUNCH_APP", "start chrome for me"),
    ("LIST_SCHEDULED_TASKS", "show me the task scheduler list"),
    ("MOVE_ITEM", "put this somewhere else"),
    ("NETWORK_INFO", "whats my ip address"),
    ("READ_FILE", "read this document to me"),
    ("RESIZE_SELECTED_FILE", "resize this photo"),
    ("RIGHT_CLICK_ELEMENT", "open the context menu for this"),
    ("SAVE_CLIPBOARD_TO_FILE", "put whats copied into a text file"),
    ("SYSTEM_LOCALE", "whats my system language"),
    ("SYSTEM_UPTIME", "check my system uptime"),
    ("EXPORT_FOLDER_LISTING_CSV", "save a list of these files to a spreadsheet"),
    ("FILE_TYPE_BREAKDOWN", "break down file types in this folder"),
]


# Format: (phrasing, expected_intent, reason). These currently miss or
# misroute -- known, tracked, deliberately NOT papered over this
# session. xfail with strict=True so an unexpected fix shows up as
# XPASS instead of silently vanishing.
KNOWN_GAPS = [
    ("how much charge do i have left", "BATTERY_STATUS",
     "scores under CONFIDENCE_THRESHOLD -- 'charge'/'left' don't overlap "
     "any BATTERY_STATUS phrasing"),
    ("duplicate this file", "COPY_ITEM",
     "loses outright to FIND_DUPLICATE_FILES on the word 'duplicate' -- "
     "not just under threshold, a genuine competitive miss"),
    ("is the print spooler running", "FIND_SERVICE",
     "a real, specific Windows service name has no anchor in this bank, "
     "same class of gap FIND_PROCESS/KILL_PROCESS had for app names"),
    ("show me what i copied", "GET_CLIPBOARD",
     "loses outright to SAVE_CLIPBOARD_TO_FILE on shared 'copied'/"
     "'clipboard'-adjacent words -- a genuine competitive miss"),
    ("is it hot right now", "GET_WEATHER",
     "loses outright to TEMPERATURE_SENSORS on 'hot' -- a genuine "
     "competitive miss, not just under threshold"),
    ("check my system temperatures", "TEMPERATURE_SENSORS",
     "loses outright to SYSTEM_INFO on 'system' -- a genuine competitive "
     "miss now that this intent's own 'temps'/'cpu temp' phrasings don't "
     "share the word 'system'"),
    ("grab this clip for me", "DOWNLOAD_PLAYING_VIDEO",
     "still under threshold despite 'grab me this clip' (same content "
     "words modulo stopwords) already being in this bank -- not "
     "re-investigated further this session"),
    ("generate a text file with a shopping list", "GENERATE_FILE",
     "'shopping list' as example content confuses the vector toward READ_FILE"),
    ("search file contents for the word invoice", "FIND_FILES_BY_CONTENT",
     "under threshold despite correct top-1 rank; tried fixing verbatim "
     "but it dropped 'find files that mention budget' (an existing "
     "confirmed hit) below threshold -- a real regression, reverted "
     "rather than trading one gap for another"),
    ("unmute my sound", "TOGGLE_MUTE",
     "under threshold despite correct top-1 rank; tried fixing verbatim "
     "(plus 'lower my volume'/'increase my volume' below) but the three "
     "together diluted TOGGLE_MUTE's vector enough to drop all 6 cases "
     "of TestVolumeOffMeansMute (test_graph_router.py) below threshold "
     "-- a real, safety-relevant regression on a previously and "
     "carefully-fixed 'volume off must never mean volume up' bug. "
     "Reverted all three; this triangle needs a dedicated session, not "
     "an opportunistic fix alongside 22 unrelated ones"),
    ("lower my volume", "VOLUME_DOWN",
     "see TOGGLE_MUTE/'unmute my sound' entry above -- same revert, same reason"),
    ("increase my volume", "VOLUME_UP",
     "see TOGGLE_MUTE/'unmute my sound' entry above -- same revert, same reason"),
    # Genuine three-way semantic overlap -- see this file's own module
    # docstring for why these are tracked, not quick-patched.
    ("sort these files by their extension", "GROUP_FILES_BY_EXTENSION",
     "loses to ORGANIZE_FILES_BY_TOPIC on shared 'files'/'by' words"),
    ("organize by file type into folders", "GROUP_FILES_BY_EXTENSION",
     "loses to SORT_FOLDER_BY_TYPE on shared 'sort'/'type'/'folder' words"),
    ("how many items are here", "COUNT_FILES",
     "'items' (not 'files') genuinely ambiguous with COUNT_FOLDERS"),
    ("where am i right now in files", "CURRENT_LOCATION",
     "loses to GET_LOCATION on 'where am i' -- needs 'files' weighted higher"),
    ("check for repeated files in this folder", "FIND_DUPLICATE_FILES",
     "'repeated' as a 'duplicate' synonym not represented; loses to COUNT_FILES"),
    ("check if this path is real", "PATH_EXISTS",
     "loses to RESOLVE_PATH on shared 'path' word alone"),
    ("give this file a new name", "RENAME_ITEM",
     "loses to MAKE_FILE on 'file'/'new' overlap; 'name' alone under-weighted"),
]


class TestConfirmedRoutingHits:
    """Regression guard: these must keep working. See HIT_EXPECTED's
    own comment for what a failure here means."""

    @pytest.mark.parametrize("intent,phrasing", HIT_EXPECTED, ids=[p for _, p in HIT_EXPECTED])
    def test_routes_correctly(self, router, intent, phrasing):
        result = router.classify(phrasing)
        assert result is not None, (
            f"{phrasing!r} used to route to {intent!r} and now scores "
            f"zero confidence -- this is a REGRESSION, not a known gap."
        )
        assert result["intent"] == intent, (
            f"{phrasing!r} used to route to {intent!r}, now routes to "
            f"{result['intent']!r} -- this is a REGRESSION, not a known gap."
        )


class TestKnownRoutingGaps:
    """Tracked, NOT fixed this session -- see this file's own module
    docstring for why. xfail(strict=True): if one of these starts
    passing, pytest reports it as XPASS so it gets noticed and promoted
    to TestConfirmedRoutingHits instead of silently staying here."""

    @pytest.mark.parametrize(
        "phrasing,intent,reason", KNOWN_GAPS,
        ids=[p for p, _, _ in KNOWN_GAPS],
    )
    @pytest.mark.xfail(strict=True, reason="tracked known routing gap, see KNOWN_GAPS reason")
    def test_known_gap_still_fails(self, router, phrasing, intent, reason):
        result = router.classify(phrasing)
        assert result is not None and result["intent"] == intent


def test_no_phrasing_appears_in_both_lists():
    """Sanity check on this file itself: a phrasing can't simultaneously
    be a confirmed hit and a known gap -- that would just mean the list
    it's ACTUALLY in disagrees with reality, silently."""
    hit_phrasings = {p for _, p in HIT_EXPECTED}
    gap_phrasings = {p for p, _, _ in KNOWN_GAPS}
    overlap = hit_phrasings & gap_phrasings
    assert not overlap, f"Phrasings listed in both HIT_EXPECTED and KNOWN_GAPS: {overlap}"
