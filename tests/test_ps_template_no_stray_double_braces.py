"""tests/test_ps_template_no_stray_double_braces.py -- BETA 0.3.67 regression
guard for a confidently-wrong bug found live-testing DISK_USAGE: its
template ("...@{{N='UsedGB';...") used `{{`/`}}` -- the escaping
convention needed when a template DOES go through `.format()` -- but
`_build_powershell_command()` (orchestrator.py) deliberately skips
`.format()` entirely for any intent with an empty `slots` list (that
skip is itself correct and load-bearing: it's what lets
windows_command_library commands keep real, unescaped PowerShell
`@{...}`/`{...}` syntax). Because DISK_USAGE has `"slots": []`, its
`{{`/`}}` was never unescaped, so the command that actually ran on a
real machine was invalid PowerShell (a literal double-brace), and it
silently produced an error-shaped response with no exception -- exactly
the "confidently wrong, not just a miss" case this codebase treats as
worse than an outright failure. NETWORK_INFO had the identical bug,
found by scanning the rest of intents.py for the same pattern once
DISK_USAGE's root cause was understood.

This test both regression-checks the two known-fixed commands directly
AND sweeps every zero-slot Tier A intent for the same "{{" opening-brace
signature so a future one written with the same (now-wrong, since these
commands skip .format()) `{{` habit fails loudly here instead of
shipping silently broken. Only opening "{{" is checked, not closing
"}}" -- valid nested PowerShell calculated-property syntax
(`@{N=...;E={...}}`) legitimately produces adjacent CLOSING braces, so
"}}" alone isn't a reliable signal; "{{" is, since valid syntax never
opens two braces back to back with nothing between them here.
"""

from intents import INTENTS
from orchestrator import _build_powershell_command


ZERO_SLOT_POWERSHELL_INTENTS = [
    name
    for name, meta in INTENTS.items()
    if meta.get("kind") == "powershell" and not meta.get("slots")
]


def test_disk_usage_has_no_stray_double_braces():
    built = _build_powershell_command(INTENTS["DISK_USAGE"], {})
    # Only opening "{{" is checked -- adjacent CLOSING braces ("}}") are
    # legitimate here (a calculated property's script block closes with
    # "}" immediately followed by the "}" that closes "@{...}" itself,
    # e.g. "...Round(...,1)}}"), so "}}" alone isn't a reliable signal.
    # "{{" is unambiguous: valid PowerShell never opens two braces back
    # to back with nothing between them in this syntax.
    assert "{{" not in built
    assert "@{N='UsedGB'" in built
    assert "@{N='FreeGB'" in built


def test_network_info_has_no_stray_double_braces():
    built = _build_powershell_command(INTENTS["NETWORK_INFO"], {})
    assert "{{" not in built
    assert "Where-Object {$_.AddressFamily" in built


def test_no_zero_slot_powershell_intent_has_unformatted_double_braces():
    """Sweep: any `kind: powershell` intent with `slots: []` runs its
    template VERBATIM (see _build_powershell_command's own comment on
    why .format() is skipped there) -- so an opening "{{" in such a
    template can never be intentional escaping, only a leftover
    mistake. (Adjacent CLOSING braces, "}}", are not checked -- see the
    two tests above for why those can be legitimate.)"""
    offenders = []
    for name in ZERO_SLOT_POWERSHELL_INTENTS:
        built = _build_powershell_command(INTENTS[name], {})
        if "{{" in built:
            offenders.append(name)
    assert not offenders, (
        f"Zero-slot PowerShell intents with an unformatted opening '{{{{' "
        f"(will run as a literal double brace, invalid syntax): {offenders}"
    )
