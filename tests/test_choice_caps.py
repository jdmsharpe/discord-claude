"""Guard against breaching Discord's 25-static-choices-per-option cap.

Discord rejects any slash-command option that declares more than 25 static
``choices`` with API error 50035. py-cord syncs ALL commands in a single
all-or-nothing bulk PUT on ``on_connect``, so a SINGLE over-limit choices list
silently aborts slash-command registration for EVERY cog in the bot — the most
catastrophic silent failure in this repo.

This test discovers every module-level ``*_CHOICES`` list in the
command-options module and asserts each stays at or under the cap, so a future
model/voice addition that breaches it fails CI instead of bricking the bot at
runtime.
"""

import pytest

from discord_claude.cogs.claude import command_options

DISCORD_MAX_CHOICES = 25


def _discover_choice_lists():
    """Yield (qualified_name, list) for every module-level ``*_CHOICES`` list.

    Counting the RESOLVED module-level object (not the AST) means generated /
    comprehension-built choice lists are measured at their true runtime length.
    """
    found = []
    for name in dir(command_options):
        if not name.endswith("_CHOICES"):
            continue
        value = getattr(command_options, name)
        if isinstance(value, list):
            found.append((f"command_options.{name}", value))
    return found


_CHOICE_LISTS = _discover_choice_lists()


def test_choice_lists_were_discovered():
    """Fail loudly if discovery finds nothing (e.g. module moved/renamed).

    Without this, a refactor that relocates the choices lists would turn the
    parametrized cap check below into a zero-test no-op that silently passes.
    """
    names = {name for name, _ in _CHOICE_LISTS}
    assert "command_options.CHAT_MODEL_CHOICES" in names, (
        f"Expected to discover CHAT_MODEL_CHOICES; found only: {sorted(names)}. "
        "Did the choices module move? Update this guard test to match."
    )


@pytest.mark.parametrize(
    ("name", "choices"),
    _CHOICE_LISTS,
    ids=[name for name, _ in _CHOICE_LISTS],
)
def test_choice_list_within_discord_cap(name, choices):
    count = len(choices)
    assert count <= DISCORD_MAX_CHOICES, (
        f"{name} has {count} choices, exceeding Discord's "
        f"{DISCORD_MAX_CHOICES}-static-choices-per-option cap. Discord rejects "
        "the whole bulk command sync with API error 50035, silently aborting "
        "slash-command registration for EVERY cog. Trim this list to "
        f"<= {DISCORD_MAX_CHOICES} entries."
    )
