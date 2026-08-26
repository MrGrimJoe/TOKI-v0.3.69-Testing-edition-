"""
test_file_convert_extraction.py -- BETA 0.3.66 (widget-context merge
session). No dedicated test file existed for
_extract_target_format()/_extract_convert_source()/FileConvertAPI.convert_selected()
before this session, which is very likely why both bugs covered here went
unnoticed:

  1. _extract_target_format(): "convert my_notes.txt into a .md file"
     used to return "txt" (the SOURCE file's own extension, found first
     by an unanchored dot-extension regex) instead of "md" (the actual
     target) -- a silent, confidently-wrong result, not a crash.

  2. FileConvertAPI.convert_selected() had no way to accept an explicit
     filename at all -- "convert notes.txt to markdown" (completely
     unambiguous) always fell through to "nothing is selected right
     now" unless the user had ALSO just dragged that exact file onto
     TOKI via selection_context.py.

Both are fixed; this file exists so they can't silently regress again.
"""

import pytest

from extractor import _extract_target_format, _extract_convert_source, extract_slots


# ─── _extract_target_format(): source-extension-mistaken-for-target bug ────

class TestTargetFormatNotConfusedWithSourceExtension:
    @pytest.mark.parametrize("text,expected", [
        ("convert my_notes.txt into a .md file", "md"),
        ("convert data.csv into a .json file", "json"),
        ("convert report.docx into a .pdf file", "pdf"),
        ("turn draft.txt into a .md file", "md"),
    ])
    def test_dot_ext_target_not_confused_with_source_extension(self, text, expected):
        result = _extract_target_format(text)
        assert result == expected, (
            f"{text!r} -> {result!r}; the SOURCE file's own extension "
            f"must never be mistaken for the TARGET format -- this is "
            f"the exact bug that made 'convert X into a .md file' return "
            f"X's own extension instead of 'md'"
        )

    @pytest.mark.parametrize("text,expected", [
        # Both of _extract_target_format's own docstring examples --
        # regression guard so the fix above doesn't narrow matching past
        # what already worked.
        ("convert this to .pdf", "pdf"),
        ("make this a .pdf", "pdf"),
        ("turn this into a text file", "txt"),
        ("convert to json", "json"),
        ("rename a.txt to a .pdf", "pdf"),
    ])
    def test_documented_examples_still_work(self, text, expected):
        assert _extract_target_format(text) == expected


# ─── _extract_convert_source(): explicit filename extraction ───────────────

class TestExplicitSourceFilenameExtraction:
    @pytest.mark.parametrize("text,expected", [
        ("convert my_notes.txt to markdown", "my_notes.txt"),
        ("convert notes.txt to markdown", "notes.txt"),
        ("convert report.docx to pdf", "report.docx"),
        ("turn my_notes.txt into a markdown file", "my_notes.txt"),
        ("convert data.csv to json", "data.csv"),
        ("can you convert notes.txt to pdf", "notes.txt"),
        ("change the file report.docx to a text file", "report.docx"),
    ])
    def test_explicit_filename_extracted_without_the_leading_verb(self, text, expected):
        result = _extract_convert_source(text)
        assert result == expected, (
            f"{text!r} -> {result!r}; _BARE_FILENAME_RE's permissive "
            f"char class (spaces included) means an unstripped leading "
            f"verb gets swallowed into the match -- this is the exact "
            f"bug that made 'convert my_notes.txt ' extract as "
            f"'convert my_notes.txt', verb included"
        )

    @pytest.mark.parametrize("text", [
        "convert it to md",
        "convert this into a .md file",
        "convert this file",
    ])
    def test_no_explicit_filename_returns_none(self, text):
        # No source filename in these -- must return None so the caller
        # falls back to selection_context (drag-drop) exactly as before,
        # never guess at a filename that isn't there.
        assert _extract_convert_source(text) is None


# ─── End-to-end: extract_slots("CONVERT_SELECTED_FILE", ...) ───────────────

class TestConvertSelectedFileSlotExtraction:
    def test_explicit_filename_and_format_both_present(self):
        slots = extract_slots("CONVERT_SELECTED_FILE", "convert notes.txt to markdown")
        assert slots is not None
        assert slots["target_format"] == "md"
        assert slots.get("explicit_source", "").lower().endswith("notes.txt")

    def test_no_filename_omits_explicit_source_key_entirely(self):
        # Drag-drop-only phrasing: explicit_source must be OMITTED (not
        # set to None/"" ) so FileConvertAPI's own `explicit_source or
        # self._current_selection_path()` fallback works -- an empty
        # string passed explicitly would short-circuit that fallback
        # exactly the same as a real one, a subtly different bug.
        slots = extract_slots("CONVERT_SELECTED_FILE", "convert this to markdown")
        assert slots is not None
        assert slots["target_format"] == "md"
        assert "explicit_source" not in slots

    def test_no_target_format_still_returns_none(self):
        # Regression guard: must still route through the missing-slot
        # ask path when no format is given at all, exactly as before
        # this session's changes.
        assert extract_slots("CONVERT_SELECTED_FILE", "convert this") is None


# ─── FileConvertAPI.convert_selected(): explicit_source parameter ──────────

class TestConvertSelectedAcceptsExplicitSource:
    def test_missing_source_message_mentions_both_options(self):
        from apis import FileConvertAPI
        api = FileConvertAPI()
        result = api.convert_selected(target_format="md")
        assert "drag a file" in result.lower()
        assert "notes.txt" in result.lower() or "name the file" in result.lower()

    def test_explicit_source_is_tried_before_selection_context(self, monkeypatch):
        from apis import FileConvertAPI
        api = FileConvertAPI()

        def _boom():
            raise AssertionError("selection_context should never be consulted "
                                  "when an explicit_source was already given")
        monkeypatch.setattr(api, "_current_selection_path", _boom)

        # A nonexistent path is fine here -- this only verifies
        # explicit_source short-circuits the selection_context lookup,
        # not that conversion itself succeeds (that's conversion_engine's
        # own, already-covered territory in test_conversion_engine.py).
        result = api.convert_selected(target_format="md", explicit_source=r"C:\nope\missing.txt")
        assert "nothing is selected" not in result.lower()
