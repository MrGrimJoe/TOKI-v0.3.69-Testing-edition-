"""
test_video_download_routing.py -- BETA 0.3.67, new.

Context: a manual sweep of ~27 natural, real-world ways someone might
ask to download a video (run directly against the live GraphRouter, not
just the phrasing bank it was built from) found roughly half of them
scoring zero confidence and falling straight through Tier A to the
LLM/web-search fallback -- confirmed live in chat ("its only currently
routing to web search due to a few gaps in my vocab"). Both
DOWNLOAD_PLAYING_VIDEO and DOWNLOAD_VIDEO_URL's phrasing banks in
graph_source_data/tier_a_phrasings.py were expanded from that sweep's
misses, and the graph was rebuilt.

This test pins that fix at the ROUTING level (classifies real strings
against the real, rebuilt graph -- same "actually run it" standard
test_wcl_coverage_audit.py and test_wcl_resolver.py already hold
themselves to) rather than only checking the phrasing bank's raw
contents, since a phrasing existing in the bank and a phrasing actually
WINNING classification against its rivals are two different claims --
TF-IDF cosine similarity means adding phrasings to one intent can shift
scores for a totally different one. audit_tier_a.py's self-consistency
sweep already guards every intent against zero-margin regressions
project-wide; this file adds a second, narrower guard specifically
for the two intents just hand-expanded, using phrasings that are
DELIBERATELY NOT copy-pasted from the phrasing bank (natural paraphrases
of it instead) -- the useful thing to verify is generalization, not that
the bank can classify itself.
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


# Paraphrases of the DOWNLOAD_PLAYING_VIDEO phrasing bank -- no source
# URL/link mentioned, since that's the real signal that distinguishes
# this intent from DOWNLOAD_VIDEO_URL below.
DOWNLOAD_PLAYING_VIDEO_PHRASINGS = [
    "download this video",
    "grab me this clip",
    "pull down this video",
    "get me this video file",
    "save this clip",
    "download this yt video",
    "get this video downloaded",
    "grab this youtube video",
    "save this to my downloads",
    "download this reel",
    "download this tiktok",
    "get the audio from this video",
    "rip the audio from this",
    "convert this video to mp3",
    "save just the audio",
    "download this song",
    "grab the mp3 from this",
    "save this youtube video to my pc",
    "get me a copy of this video",
    "grab this video off the web",
    "download this clip im watching",
    "download this vid for me",
    "download this mp4",
    "can you download this youtube video",
]

# Paraphrases of the DOWNLOAD_VIDEO_URL phrasing bank -- these all name a
# link/url/address as the explicit source, unlike the list above.
DOWNLOAD_VIDEO_URL_PHRASINGS = [
    "download the video at this url",
    "download this video from youtube.com/watch?v=abc",
    "download this video from this link",
    "save this url as a video",
    "download the video from this address",
    "grab the video at this address",
    "download this youtube url",
    "save the video from this link to my pc",
    "pull down the video from this url",
    "get the video from this link",
]


class TestDownloadPlayingVideoRouting:
    @pytest.mark.parametrize("phrasing", DOWNLOAD_PLAYING_VIDEO_PHRASINGS)
    def test_routes_to_download_playing_video(self, router, phrasing):
        result = router.classify(phrasing)
        assert result is not None, (
            f"{phrasing!r} scored zero confidence against every intent "
            "and would fall through to the LLM/web-search fallback -- "
            "this is exactly the reported routing gap this test guards."
        )
        assert result["intent"] == "DOWNLOAD_PLAYING_VIDEO", (
            f"{phrasing!r} routed to {result['intent']!r} instead"
        )


class TestDownloadVideoUrlRouting:
    @pytest.mark.parametrize("phrasing", DOWNLOAD_VIDEO_URL_PHRASINGS)
    def test_routes_to_download_video_url(self, router, phrasing):
        result = router.classify(phrasing)
        assert result is not None, (
            f"{phrasing!r} scored zero confidence against every intent "
            "and would fall through to the LLM/web-search fallback."
        )
        assert result["intent"] == "DOWNLOAD_VIDEO_URL", (
            f"{phrasing!r} routed to {result['intent']!r} instead"
        )


class TestDownloadRoutingDoesNotStealOtherIntents:
    """The other half of the regression risk: expanding these two
    intents' phrasing banks must not start winning classification for
    phrasings that genuinely belong to a different intent (a copy/paste
    or a too-loose new phrasing could easily cause this silently)."""

    def test_generic_file_copy_does_not_route_to_download_intents(self, router):
        result = router.classify("copy this file to my desktop")
        if result is not None:
            assert result["intent"] not in (
                "DOWNLOAD_PLAYING_VIDEO", "DOWNLOAD_VIDEO_URL",
            )

    def test_generic_save_clipboard_does_not_route_to_download_intents(self, router):
        result = router.classify("save the clipboard to a file")
        if result is not None:
            assert result["intent"] not in (
                "DOWNLOAD_PLAYING_VIDEO", "DOWNLOAD_VIDEO_URL",
            )

    def test_plain_convert_request_does_not_route_to_download_intents(self, router):
        result = router.classify("convert this document to a pdf")
        if result is not None:
            assert result["intent"] not in (
                "DOWNLOAD_PLAYING_VIDEO", "DOWNLOAD_VIDEO_URL",
            )
