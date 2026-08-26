"""
tests/test_move_copy_context_e2e.py

Real, on-disk end-to-end coverage for resolve_move_or_copy_with_context()
(extractor.py) and the "put/place/drop X in Y" pre-check (orchestrator.py)
-- the "put it in function" feature.

WHY THIS FILE EXISTS
---------------------
Every other test covering this feature (test_extractor.py,
test_orchestrator.py) checks the PYTHON side only: the right slots get
resolved, the right MOVE_ITEM/COPY_ITEM command STRING gets built. None of
them actually run that command against a real file on disk -- that was an
explicitly flagged open caveat when this feature shipped ("I haven't
watched the actual Move-Item execute against a real filesystem, just
confirmed the command string it builds is correct").

WHY THIS CAN'T JUST MONKEYPATCH ITS WAY AROUND THAT (found writing this
file, not assumed)
---------------------------------------------------------------------------
The obvious first attempt was to reuse tests/test_file_index.py's own
`sandbox` fixture pattern -- monkeypatch extractor.get_sandbox_roots() to
a real tmp_path and check the real filesystem. That does NOT work here,
and finding out why is itself a real result: extractor.py's whole path
layer deliberately uses `ntpath`, not `os.path`, everywhere (see
get_sandbox_roots()'s own docstring: "this app only ever runs on
Windows, regardless of what platform it's developed/tested on") --
meaning resolve_path() always returns a BACKSLASH-joined string
(confirmed directly: resolve_path("Homework", "/tmp/Desktop") returns
'\\tmp\\Desktop\\Homework', not '/tmp/Desktop/Homework'). Handed to
os.makedirs() on a real Linux/macOS dev box, that backslash string isn't
a nested path at all -- backslash is just a normal filename character on
those platforms -- so it creates ONE garbage directory literally named
"tmp\\Desktop\\Homework" sitting in the current working directory. (This
is exactly what produced a stray "C:\\Users\\Default\\Desktop\\function"
folder during this feature's own manual testing, cleaned up before
shipping.) So a monkeypatched-sandbox test on a non-Windows box would
"pass" while silently verifying the wrong thing -- worse than an honest
failure.

So: the directory-auto-create half AND the Move-Item execution half both
genuinely require running on a machine where backslash is the real path
separator -- i.e. Windows, TOKI's actual deployment target. Both test
classes below check `sys.platform == "win32"` and FAIL LOUDLY (not
skipped) with an explicit message if not. A skip would let "does this
actually work on a real filesystem" go quietly unverified forever, which
is exactly the gap this file exists to close. If you are seeing one of
these failures:

    RUN THIS FILE ON A REAL WINDOWS MACHINE (or any Windows box/VM) via:

        python -m pytest tests/test_move_copy_context_e2e.py -v

    and confirm both classes below pass there. Until that's been done at
    least once, the real-filesystem execution path for the move/copy
    context feature is UNVERIFIED -- don't consider it done.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from extractor import resolve_move_or_copy_with_context
from orchestrator import _build_powershell_command, _intent_meta


def _require_windows() -> None:
    if sys.platform != "win32":
        pytest.fail(
            "\n\n"
            "NOT RUNNING ON WINDOWS.\n"
            "This test verifies the 'put it in <folder>' feature against a "
            "REAL directory/file on disk -- not just a computed path string. "
            "extractor.py's path layer is deliberately ntpath-based (Windows "
            "backslash paths) throughout, by design (see this module's own "
            "docstring for the full reasoning), so that can only be honestly "
            "verified where backslash is actually the real path separator: "
            "on Windows.\n\n"
            "ACTION NEEDED: run this test on a real Windows machine (TOKI's "
            "actual deployment target) via:\n"
            "    python -m pytest tests/test_move_copy_context_e2e.py -v\n"
            "and confirm it passes there. Until that's done, this part of "
            "the feature is UNVERIFIED against a real filesystem.\n"
        )


def _find_real_powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


@pytest.fixture
def real_desktop_sandbox(tmp_path, monkeypatch):
    """Only ever used after _require_windows() has already passed, so
    tmp_path here is a real Windows temp directory and ntpath's
    backslash joining matches the OS's own separator -- unlike the
    generic cross-platform `sandbox` fixture in test_file_index.py, this
    one is specifically for tests that need the RESULT to be a real,
    correctly-nested directory on disk, not just a plausible-looking
    string."""
    import extractor
    desktop = tmp_path / "Desktop"
    d_drive = tmp_path / "DDrive"
    desktop.mkdir()
    d_drive.mkdir()
    monkeypatch.setattr(extractor, "get_sandbox_roots",
                         lambda: [str(d_drive), str(desktop)])
    return desktop


class TestRealDirectoryAutoCreation:
    """The bare-folder-name auto-create step is pure Python (os.makedirs)
    -- no PowerShell involved -- but still needs a real Windows-style
    filesystem to mean anything (see module docstring)."""

    def test_new_bare_folder_name_is_really_created_on_disk(self, real_desktop_sandbox):
        _require_windows()
        src = real_desktop_sandbox / "screenshot_test.png"
        src.write_bytes(b"fake png bytes")

        slots = resolve_move_or_copy_with_context(
            "MOVE_ITEM", "now put it in function", {"path": str(src)}, {},
        )

        assert slots is not None
        expected_dest = real_desktop_sandbox / "function"
        assert Path(slots["dest"]) == expected_dest
        assert expected_dest.is_dir(), (
            f"resolve_move_or_copy_with_context() returned dest={slots['dest']!r} "
            f"but no real directory exists there -- the auto-create step "
            f"(os.makedirs) silently failed to actually create it."
        )

    def test_existing_folder_is_reused_not_duplicated(self, real_desktop_sandbox):
        _require_windows()
        (real_desktop_sandbox / "Homework").mkdir()
        src = real_desktop_sandbox / "essay.txt"
        src.write_text("")

        slots = resolve_move_or_copy_with_context(
            "MOVE_ITEM", "put it in Homework", {"path": str(src)}, {},
        )

        assert slots is not None
        assert Path(slots["dest"]) == real_desktop_sandbox / "Homework"
        dirs = [p.name for p in real_desktop_sandbox.iterdir() if p.is_dir()]
        assert dirs == ["Homework"], (
            f"expected exactly the one real folder to be reused, found: {dirs}"
        )


class TestMoveItemRealPowerShellExecution:
    """Runs the real, generated Move-Item command through a real
    PowerShell interpreter against a real file. See this module's own
    docstring for exactly what to do if this fails on your machine."""

    def test_put_it_in_bare_folder_name_actually_moves_the_real_file(self, real_desktop_sandbox):
        _require_windows()
        ps_binary = _find_real_powershell()
        if ps_binary is None:
            pytest.fail(
                "Running on Windows but no powershell.exe/pwsh was found on "
                "PATH -- can't execute the real Move-Item command. Install "
                "PowerShell and re-run this test."
            )

        src = real_desktop_sandbox / "screenshot_test.png"
        src.write_bytes(b"fake png bytes")

        slots = resolve_move_or_copy_with_context(
            "MOVE_ITEM", "now put it in function", {"path": str(src)}, {},
        )
        assert slots is not None, "slot resolution itself failed -- fix that before the execution check even matters"

        meta = _intent_meta("MOVE_ITEM")
        command = _build_powershell_command(meta, slots)

        # Same subprocess shape as executor.RunningCommand._run().
        proc = subprocess.run(
            [ps_binary, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=30,
        )

        assert proc.returncode == 0, (
            f"Move-Item exited {proc.returncode}.\n"
            f"Command: {command}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

        moved_path = Path(slots["dest"]) / "screenshot_test.png"
        assert moved_path.exists(), (
            f"PowerShell reported success (exit 0) but the file isn't "
            f"actually at {moved_path}.\n"
            f"Command: {command}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        assert not src.exists(), "source file should no longer exist after a real MOVE"
        assert moved_path.read_bytes() == b"fake png bytes"
