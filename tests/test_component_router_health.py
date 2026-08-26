"""
test_component_router_health.py -- BETA 0.3.67, new.

Context: this session found that KuzuComponentRouter and GraphRouter each
independently opening a kuzu.Database on the same toki_graph_db directory
reliably raises a lock error on Windows (works by accident on Linux) --
and because orchestrator.py wraps component_router's construction in a
silent `try/except Exception: component_router = None`, that lock error
never surfaced anywhere. It just silently left component_router as None
on every real Windows run since the component-graph routing layer was
added. See component_router_kuzu.py's own KuzuComponentRouter.__init__
docstring and orchestrator.py's construction site for the full story and
the fix (sharing one kuzu.Database handle instead of opening two).

The fix itself is exercised indirectly by tests/test_launch_app_run_alias.py
and tests/test_open_cascade_integration.py (both of which silently broke
because of the exact failure mode this bug caused) -- but neither of them
actually ASSERTS that a real, unmocked WindowsAIAssistant() ends up with
a live component_router. This file closes that gap directly: it's the
one test that would fail LOUDLY, with a clear message pointing at the
actual cause, if this exact bug class ever reappears (e.g. a future
refactor reintroduces a second kuzu.Database open on the same
directory), instead of silently degrading back to graph-only routing
with nothing anywhere saying so.
"""

import pytest

pytest.importorskip("kuzu")

from graph_router import DB_PATH

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="toki_graph_db not present in this checkout -- run migrate_to_kuzu.py first",
)


class TestComponentRouterIsActuallyLive:
    def test_fresh_assistant_gets_a_live_component_router(self):
        """The concrete regression this bug caused: a plain, real
        WindowsAIAssistant() -- no mocking, exactly how app.py's own
        startup constructs one -- must end up with an actual
        KuzuComponentRouter instance wired into its LayeredGraphRouter,
        not silently None. If this ever fails again, the fix documented
        in component_router_kuzu.py's KuzuComponentRouter.__init__
        docstring has regressed -- check for a reintroduced SECOND
        kuzu.Database() open on the same directory first."""
        import orchestrator

        assistant = orchestrator.WindowsAIAssistant()
        try:
            assert assistant.graph_router is not None, (
                "graph_router itself is None -- GraphRouter() failed to "
                "construct at all, a more basic problem than the "
                "component_router issue this test targets."
            )
            component_router = getattr(assistant.graph_router, "component_router", None)
            assert component_router is not None, (
                "component_router is None on a fresh, real "
                "WindowsAIAssistant() -- this is exactly the silent "
                "production failure mode fixed this session (see "
                "component_router_kuzu.py's KuzuComponentRouter.__init__ "
                "docstring). Most likely cause: something is once again "
                "opening a second, independent kuzu.Database() on the "
                "same toki_graph_db directory instead of reusing "
                "graph_router.db."
            )
        finally:
            if hasattr(assistant, "shutdown"):
                assistant.shutdown()

    def test_component_router_shares_the_graph_routers_database_object(self):
        """More precise than the test above: not just 'non-None', but
        specifically THE SAME kuzu.Database object as the GraphRouter's
        own -- confirming the fix's actual mechanism (reuse, not a
        second independent open that happened not to fail this time)."""
        import orchestrator

        assistant = orchestrator.WindowsAIAssistant()
        try:
            component_router = getattr(assistant.graph_router, "component_router", None)
            if component_router is None:
                pytest.fail(
                    "component_router is None -- see "
                    "test_fresh_assistant_gets_a_live_component_router "
                    "for the full explanation; that test's failure "
                    "message is the one to act on."
                )
            assert component_router.db is assistant.graph_router.tfidf_router.db, (
                "component_router.db is a DIFFERENT object than the "
                "wrapped GraphRouter's (LayeredGraphRouter.tfidf_router) "
                "own .db -- meaning something is back to opening a "
                "second independent kuzu.Database() on the same "
                "directory. It may have gotten lucky and not raised a "
                "lock error THIS time (e.g. running on Linux), but the "
                "fix's whole point was to never do this at all."
            )
        finally:
            if hasattr(assistant, "shutdown"):
                assistant.shutdown()
