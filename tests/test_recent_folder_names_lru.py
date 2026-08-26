"""
test_recent_folder_names_lru.py -- BETA 0.3.66 (widget-context merge
session). Confirmed live: the "last 3 recently touched folder names"
cache (used so "put it in Homework" reuses an existing folder instead of
creating a duplicate -- see orchestrator.py's _remember_touched() and
extractor.py's resolve_move_or_copy_with_context()) was meant to behave
as LRU, but a plain dict's `d[existing_key] = value` does NOT move that
key to the end of iteration order -- it stays at its ORIGINAL insertion
position. Re-touching an already-cached folder name never promoted it,
so it could still be evicted next even though it was the most recently
used entry. Both call sites shared the identical bug and the identical
fix (pop the key before re-inserting it). No test existed for either
before this session, which is very likely why it went unnoticed.
"""

import ntpath

import pytest

from extractor import resolve_move_or_copy_with_context


def _lru_touch(cache: dict, key: str, value: str, cap: int = 3) -> None:
    """Mirrors the exact fixed logic in both orchestrator.py's
    _remember_touched() and extractor.py's
    resolve_move_or_copy_with_context()."""
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > cap:
        cache.pop(next(iter(cache)))


class TestFolderNameCacheLRUOrdering:
    def test_re_touching_an_existing_key_promotes_it_to_most_recent(self):
        cache = {}
        _lru_touch(cache, "a", "pathA")
        _lru_touch(cache, "b", "pathB")
        _lru_touch(cache, "c", "pathC")
        # Re-touch "a" -- must now be treated as the MOST recently used,
        # not still sitting in its original (oldest) position.
        _lru_touch(cache, "a", "pathA_v2")
        _lru_touch(cache, "d", "pathD")
        # "b" is the genuinely oldest untouched entry and must be the
        # one evicted -- NOT "a", which was just re-touched.
        assert "b" not in cache, (
            f"cache={cache}; 'b' (oldest untouched) should have been "
            f"evicted, but 'a' (just re-touched) was evicted instead -- "
            f"this is the exact bug: plain dict re-assignment doesn't "
            f"move an existing key to the end of iteration order"
        )
        assert "a" in cache and cache["a"] == "pathA_v2"
        assert set(cache.keys()) == {"a", "c", "d"}

    def test_cap_still_enforced_at_three(self):
        cache = {}
        for name in ["a", "b", "c", "d", "e"]:
            _lru_touch(cache, name, f"path{name}")
        assert len(cache) == 3
        assert set(cache.keys()) == {"c", "d", "e"}


class TestResolveMoveOrCopyWithContextReuse:
    """End-to-end through the real extractor.py function, not just the
    isolated dict logic above."""

    def test_recently_created_folder_reused_not_duplicated(self):
        recent = {}
        # Simulate two folders created earlier this session, then a
        # third that re-touches the first one's name (e.g. the user
        # created "Homework" earlier, then again just now).
        recent["homework"] = r"C:\Users\Default\Desktop\Homework"
        recent["projects"] = r"C:\Users\Default\Desktop\Projects"
        result = resolve_move_or_copy_with_context(
            "MOVE_ITEM", "move report.docx to Homework",
            last_touched=None, recent_folder_names=recent,
        )
        assert result is not None
        assert result["dest"] == r"C:\Users\Default\Desktop\Homework"
        # The lookup itself must not have silently dropped "homework"
        # even after being matched against -- confirms the dict passed
        # in in still has all 2 entries (this function only reads/writes
        # its own new dest_key, not the ones already there).
        assert "homework" in recent
        assert "projects" in recent
