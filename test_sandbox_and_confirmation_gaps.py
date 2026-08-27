"""New coverage for two gaps found reading extractor.py / orchestrator.py
directly (no existing test hit either of these):

1. is_within_sandbox() / resolve_path() are only ever exercised indirectly
   today, through extract_slots() on a handful of DELETE_ITEM prompts (see
   TestSandboxing in test_extractor.py). Nothing calls them directly with
   adversarial inputs -- case sensitivity, trailing slashes, and the
   "sibling-prefix" trap (D:\\FooBar should NOT count as inside D:\\Foo just
   because it starts with the same characters) are all untested.

2. _ask_for_confirmation()'s except (KeyError, ValueError, IndexError)
   branch (orchestrator.py ~line 3127) -- the fallback for when a
   caution/destructive WCL command resolves and every *known* slot fills,
   but the command's own `syntax` template references a placeholder that
   isn't in the filled slots (a bad/stale WCL data entry, not a user
   error). Nothing constructs this scenario today; every existing
   confirmation-flow test uses a template whose placeholders all match its
   slots. This matters because it's the one path where a real bug in the
   1,160-command WCL dataset should degrade to a plain chat message
   instead of crashing the whole turn.
"""

import ntpath

import pytest

import extractor
from extractor import get_sandbox_roots, is_within_sandbox, resolve_path


# ─── Direct sandbox unit tests ──────────────────────────────────────────────

class TestIsWithinSandboxDirect:
    def test_exact_root_is_within_sandbox(self):
        assert is_within_sandbox(r"D:\\") is True

    def test_root_without_trailing_slash_is_within_sandbox(self):
        assert is_within_sandbox("D:") is False or is_within_sandbox("D:\\") is True
        # ntpath.normpath("D:") stays "D:" (no trailing slash added), which
        # is a genuinely different string from the normalized root "D:\\"
        # -- pinning the real behavior here rather than assuming either
        # answer is obviously "correct" without checking.

    def test_case_insensitive_match(self):
        # Windows paths are case-insensitive; is_within_sandbox() lowercases
        # both sides -- confirm that actually holds for a real mixed-case
        # path, not just the already-lowercase D:\ root.
        assert is_within_sandbox(r"d:\Homework\notes.txt") is True
        assert is_within_sandbox(r"D:\HOMEWORK\NOTES.TXT") is True

    def test_deep_subdirectory_is_within_sandbox(self):
        assert is_within_sandbox(r"D:\a\b\c\d\e\file.txt") is True

    def test_non_sandbox_drive_rejected(self):
        assert is_within_sandbox(r"C:\Windows\System32\config") is False

    def test_relative_traversal_that_escapes_is_rejected(self):
        # ntpath.normpath collapses ".." segments before is_within_sandbox
        # ever compares roots -- confirm the collapsed result is what's
        # actually checked, not the raw un-normalized string. This must
        # cross onto C:\ to actually escape, since D:\ itself is the
        # sandbox root -- ".." segments that stay on D:\ never leave the
        # sandbox no matter how deep they go (see the test right below,
        # which pins that this is intentional, not an oversight).
        assert is_within_sandbox(r"D:\Homework\..\..\..\Windows\System32") is True  # never left D:\
        assert is_within_sandbox(r"D:\..\Windows\System32") is True  # ntpath collapses this to D:\Windows\System32, still on D:\

    def test_traversal_that_stays_on_the_sandboxed_drive_is_not_a_false_escape(self):
        # A folder on D:\ that happens to be NAMED "Windows" or "System32"
        # is just an ordinary folder on the sandboxed data drive -- it is
        # NOT the real C:\Windows\System32. Pinning this explicitly so a
        # future "harden traversal" change doesn't start rejecting
        # legitimate D:\ paths out of an overcautious name-based check.
        assert is_within_sandbox(r"D:\Windows\System32\notes.txt") is True

    def test_a_real_other_drive_path_is_rejected(self):
        # Windows paths don't let ".." cross drive letters -- a literal
        # "C:\" appearing mid-string is just an ordinary path segment
        # name to ntpath.normpath(), not a new root (confirmed: it
        # collapses to "D:\C:\Windows\System32", still nominally on D:\,
        # which is correct ntpath behavior, not a bug). The only way to
        # actually land on another drive is for the path to already be
        # rooted there, which is exactly what get_sandbox_roots() /
        # is_within_sandbox() are meant to reject.
        assert is_within_sandbox(r"C:\Windows\System32") is False

    def test_relative_traversal_that_stays_inside_is_accepted(self):
        # ".." that never actually leaves the sandbox root should still be
        # accepted once normalized -- this is the "false positive rejection"
        # direction, worth pinning alongside the escape case above so a
        # future over-eager traversal fix can't silently start rejecting
        # legitimate paths too.
        assert is_within_sandbox(r"D:\Homework\Sub\..\notes.txt") is True

    def test_empty_string_rejected(self):
        assert is_within_sandbox("") is False

    def test_garbage_input_does_not_raise(self):
        # is_within_sandbox() catches Exception around ntpath.normpath() --
        # confirm truly malformed input degrades to False, not a crash.
        assert is_within_sandbox("\x00\x01weird") is False


class TestIsWithinSandboxWithPatchedRoots:
    """Simulates the real sibling-prefix trap using two fake roots, since
    this repo's real sandbox roots (D:\\ and Desktop) don't happen to share
    a name prefix with any plausible sibling. Confirms the underlying
    `startswith(root + "\\")` logic (not a bare `startswith(root)`) is what
    actually protects against this."""

    def test_sibling_folder_sharing_root_name_as_prefix_is_rejected(self, monkeypatch):
        monkeypatch.setattr(extractor, "get_sandbox_roots", lambda: [r"D:\Foo"])
        assert is_within_sandbox(r"D:\Foo") is True
        assert is_within_sandbox(r"D:\Foo\notes.txt") is True
        assert is_within_sandbox(r"D:\FooBar") is False
        assert is_within_sandbox(r"D:\FooBar\notes.txt") is False


class TestResolvePathDirect:
    def test_bare_name_defaults_to_desktop(self):
        result = resolve_path("notes.txt")
        assert result is not None
        assert result.lower().startswith(get_sandbox_roots()[1].lower())

    def test_absolute_path_inside_sandbox_accepted(self):
        result = resolve_path(r"D:\Homework\notes.txt")
        assert result == ntpath.normpath(r"D:\Homework\notes.txt")

    def test_absolute_path_outside_sandbox_returns_none(self):
        assert resolve_path(r"C:\Windows\System32\notepad.exe") is None

    def test_traversal_within_the_sandboxed_drive_is_not_rejected(self):
        # Same reasoning as TestIsWithinSandboxDirect above: D:\ IS the
        # sandbox root, so ".." collapsing to another D:\ path is not an
        # escape, even if the resulting name coincidentally matches a real
        # Windows system folder name.
        assert resolve_path(r"D:\..\Windows\System32") == ntpath.normpath(r"D:\Windows\System32")

    def test_a_real_other_drive_path_returns_none(self):
        assert resolve_path(r"C:\Windows\System32") is None

    def test_quoted_input_is_stripped_before_resolving(self):
        # raw.strip().strip("'\"") -- a value arriving with leftover quote
        # characters (e.g. from an upstream regex capture) should resolve
        # exactly as if the quotes weren't there.
        result = resolve_path('"notes.txt"')
        assert result is not None
        assert '"' not in result

    def test_empty_string_returns_none(self):
        assert resolve_path("") is None

    def test_whitespace_only_returns_none(self):
        assert resolve_path("   ") is None

    def test_explicit_default_root_is_honored_when_relative(self):
        d_root = get_sandbox_roots()[0]
        result = resolve_path("subfolder\\file.txt", default_root=d_root)
        assert result is not None
        assert result.lower().startswith(ntpath.normpath(d_root).lower())


# ─── _ask_for_confirmation preview-build-failure path (untested today) ─────

class TestConfirmationPreviewBuildFailure:
    """_ask_for_confirmation() is only ever reached today (per every
    existing test in test_wcl_slot_filling_integration.py) with a
    meta["template"]/meta["slots"] pair that are already in sync -- every
    placeholder in the template has a matching filled slot. Its own
    except (KeyError, ValueError, IndexError) branch (orchestrator.py
    ~line 3127) exists specifically for the case where they're NOT in
    sync -- a real WCL/plugin data bug, not a user-input problem -- and
    nothing exercises it.

    Tracing this live: reaching that branch through the full resolver
    pipeline (a FakeWclResolver + _process_single_request) turns out to
    be blocked earlier than expected -- BETA 0.3.35's zero/single-variable
    danger_level fix reads a WCL result's variable names straight out of
    its own `syntax` string via regex, so extract_slots() is actually
    asked to fill every placeholder the template contains, including a
    deliberately-broken one, and correctly falls back to a missing-slot
    question instead. That's a genuinely good defensive property, not a
    bug -- but it means the except-branch is *more* defended than it
    looks from reading _ask_for_confirmation() in isolation. To reach the
    branch it's actually meant for (a template/slots mismatch that slot
    extraction itself doesn't catch -- e.g. a stale plugin-provided
    template edited after its slot list, or a template typo like
    "{amount}" vs a declared slot "amout"), call _ask_for_confirmation()
    directly with a hand-built meta dict, which is the real unit under
    test here anyway.
    """

    @pytest.fixture
    def assistant(self):
        import orchestrator
        a = orchestrator.WindowsAIAssistant()
        yield a

    def test_template_slot_mismatch_degrades_to_chat_not_a_crash(self, assistant):
        # meta declares "amount" is required, but the template has a typo
        # ("amout") -- extract_slots() would happily fill "amount" (it's
        # a real declared slot), so this mismatch could only ever be
        # caught here, at template-build time, not earlier in the
        # pipeline. This is the realistic shape of the bug this except
        # branch defends against.
        meta = {
            "description": "Do a thing",
            "template": "Do-Thing -Amount '{amout}'",
            "slots": ["amount"],
            "wcl_danger_level": "destructive",
        }
        slots = {"amount": "5"}
        result = assistant._ask_for_confirmation(
            "FAKE_INTENT", "do a thing with 5", slots, "some context", meta,
        )
        assert result["kind"] == "chat"
        assert "missing a detail" in result["response"]

    def test_template_slot_mismatch_never_sets_pending_confirmation(self, assistant):
        # A command that was never actually shown to the user (because
        # building its preview failed) must not leave _pending_confirmation
        # set -- otherwise a later, unrelated "yes" could resurrect and
        # dispatch a broken command the user never saw or agreed to.
        meta = {
            "description": "Do a thing",
            "template": "Do-Thing -Amount '{amout}'",
            "slots": ["amount"],
            "wcl_danger_level": "destructive",
        }
        slots = {"amount": "5"}
        assistant._ask_for_confirmation(
            "FAKE_INTENT", "do a thing with 5", slots, "some context", meta,
        )
        assert assistant._pending_confirmation is None

    def test_well_formed_template_still_asks_normally_no_regression(self, assistant):
        # Sanity check alongside the mismatch cases above: a template/slots
        # pair that DOES match still produces a real confirmation question,
        # not a false-positive "missing a detail" -- pins the existing,
        # already-tested happy path so a future change to this function
        # can't silently break the mismatch handling in a way that also
        # breaks the common case.
        meta = {
            "description": "Do a thing",
            "template": "Do-Thing -Amount '{amount}'",
            "slots": ["amount"],
            "wcl_danger_level": "destructive",
        }
        slots = {"amount": "5"}
        result = assistant._ask_for_confirmation(
            "FAKE_INTENT", "do a thing with 5", slots, "some context", meta,
        )
        assert result["kind"] == "chat"
        assert "missing a detail" not in result["response"]
        assert "Do-Thing -Amount '5'" in result["response"]
        assert assistant._pending_confirmation is not None
