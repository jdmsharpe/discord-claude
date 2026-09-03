"""Guard against a slash-command option advertising a default it no longer uses.

Discord renders an option's ``description`` verbatim in the command picker, so a
description ending ``(default: Claude Opus 4.5)`` while the option's real
``default`` is ``claude-opus-5`` shows WRONG INFORMATION TO USERS — the bot
quietly does one thing while its own UI promises another. Every instance of this
drift found across this bot fleet traced back to a "promote the newer default"
commit that changed the value and forgot the sentence next to it.

This test walks the cog's real ``SlashCommandGroup`` objects, so options added
later are covered with no edits here, and asserts that any option carrying BOTH
static ``choices`` AND a stated ``(default: X)`` names the choice its ``default``
actually resolves to.

Scope is deliberately narrow. Options with no ``choices``, or whose ``default``
is ``None``, are NOT asserted over: their effective default is usually applied
downstream (in ``_build_api_params``, in the SDK, or by Anthropic itself) where
introspection cannot see it, and asserting over them produced dozens of false
alarms. A guard that cries wolf gets muted, which is worse than no guard. An
option whose ``default`` resolves to none of its own choices is a different bug
class this guard cannot describe accurately, so it is counted and reported as
UNASSERTABLE rather than quietly folded into the passing set.

The acceptance rule was tightened twice after review, and both fixes are pinned
by the matcher case table below so neither can regress:

* A description is NOT accepted merely because the display name starts with the
  claimed text. That let a "Foo 1" -> "Foo 1.5" promotion sail through on a
  stale "Foo 1" claim, which is precisely the drift this guard exists to catch.
  Only a trailing parenthetical may be trimmed, matched against the stem.
* A description is NOT accepted when the claim EXTENDS the real name either.
  Plain substring containment found "Claude Opus 5" inside a claim of
  "Claude Opus 5.1", so promoting 5 -> 5.1 with a stale description still
  passed. Every match is now anchored with ``NOT_EXTENDED``, a lookahead that
  rejects a continuation into a longer identifier (a word character, a hyphen,
  or a dot followed by a digit) while still allowing ordinary sentence
  punctuation, because real descriptions contain exactly that:
  "(default: Claude Opus 5. warning: Opus is expensive!)".

The raw-value acceptance is additionally guarded against an empty value, since
``"" in claimed`` is always True and silently accepted arbitrary wrong text.
"""

import re

import discord
import pytest

from discord_claude.cogs.claude.cog import ClaudeCog

DEFAULT_CLAUSE_RE = re.compile(r"\(default:\s*([^)]+)\)", re.IGNORECASE)
TRAILING_PAREN_RE = re.compile(r"\s*\(.*")

# A match may not run on into a LONGER identifier: a word character, a hyphen, or
# a dot immediately followed by a digit ("Claude Opus 5" must not match inside a
# claim of "Claude Opus 5.1" or "Claude Opus 5-preview"). Sentence punctuation —
# ". ", ";", ",", "!" — is deliberately still allowed through.
NOT_EXTENDED = r"(?![\w-])(?!\.\d)(?!\s+\w)"


def _description_names_default(display_name: str, raw_value: object, claimed: str) -> bool:
    """Return whether ``claimed`` text credibly names the ``display_name`` choice.

    Exactly four things are accepted, each anchored by ``NOT_EXTENDED`` so the
    claim cannot silently name a longer, different identifier:

    1. the lowercased display name appears somewhere in the claimed text;
    2. the claimed text equals the display-name stem (the name with any trailing
       parenthetical removed), e.g. "Claude Fable 5" for "Claude Fable 5 (Preview)";
    3. the claimed text starts with that stem, since descriptions sometimes add
       prose after the name, e.g. "Claude Opus 5. warning: Opus is expensive!";
    4. the raw default value is non-empty AND appears in the claimed text, e.g.
       "1:1" where the choice is named "Square (1:1)".
    """
    name = (display_name or "").strip().lower()
    value = str(raw_value or "").strip().lower()
    claim = (claimed or "").strip().lower()
    if not name or not claim:
        return False
    stem = TRAILING_PAREN_RE.sub("", name).strip()
    if re.search(re.escape(name) + NOT_EXTENDED, claim):
        return True
    if stem and claim == stem:
        return True
    if stem and re.match(re.escape(stem) + NOT_EXTENDED, claim):
        return True
    return bool(value and re.search(re.escape(value) + NOT_EXTENDED, claim))


# Fixed cases that pin the matcher itself, independent of what discovery finds in
# this repo. They run even if the cog has zero in-scope options, so the rule can
# never be rendered vacuous by a refactor. Shared verbatim across the fleet.
_MATCHER_CASES = [
    (
        "Gemini 3.7 Flash",
        "gemini-3.7-flash",
        "Gemini 3.7 Flash Pro",
        False,
        "space-extended superset drift: the claim names a longer, different model",
    ),
    ("GPT Image 2", "gpt-image-2", "GPT Image 1.5", False, "real drift"),
    (
        "GPT Image 1.5",
        "gpt-image-1.5",
        "GPT Image 1",
        False,
        "prefix-superset drift (v3 hole)",
    ),
    (
        "Claude Opus 5",
        "claude-opus-5",
        "Claude Opus 5.1",
        False,
        "SUPERSET drift (v4 hole)",
    ),
    (
        "Claude Opus 5",
        "claude-opus-5",
        "Claude Opus 5. warning: Opus is expensive!",
        True,
        "sentence punctuation after name",
    ),
    (
        "Grok Imagine Video 1.5 (Preview)",
        "grok-imagine-video-1.5-preview",
        "Grok Imagine Video 1.5",
        True,
        "trailing parenthetical trimmed",
    ),
    (
        "Deep Research (Apr 2026)",
        "deep-research-preview-04-2026",
        "Deep Research; Max for best reports",
        True,
        "prose after the stem",
    ),
    ("Square (1:1)", "1:1", "1:1", True, "description uses the raw value"),
    ("Kore (Firm)", "Kore", "Kore", True, "value spelling"),
    ("Gemini 3.7 Flash", "gemini-3.7-flash", "Gemini 3.6 Flash", False, "real drift"),
    ("Anything", "", "total nonsense", False, "empty value must not vacuously accept"),
    (
        "Gemini 3.1 Flash Preview TTS",
        "gemini-3.1-flash-tts-preview",
        "Gemini 2.5 Flash Preview TTS",
        False,
        "real drift",
    ),
]


@pytest.mark.parametrize(
    ("display_name", "raw_value", "claimed", "expected", "why"),
    _MATCHER_CASES,
    ids=[
        f"{'accepts' if expected else 'rejects'}: {display_name} vs {claimed}"
        for display_name, _, claimed, expected, _ in _MATCHER_CASES
    ],
)
def test_matcher_accepts_only_real_matches(display_name, raw_value, claimed, expected, why):
    accepted = _description_names_default(display_name, raw_value, claimed)
    assert accepted is expected, (
        f"Matcher {'rejected' if expected else 'accepted'} "
        f"claimed={claimed!r} for choice {display_name!r} (value {raw_value!r}); "
        f"expected it to be {'accepted' if expected else 'rejected'} — {why}."
    )


def _discover_defaulted_choice_options():
    """Return (assertable, unassertable) option tuples for the cog's slash commands.

    Walking the RESOLVED ``SlashCommandGroup`` objects on the cog class (not the
    source text) means every current and future subcommand option is covered
    automatically, including any built by a decorator or a helper.

    An option is assertable only if it has ``choices`` AND a non-``None``
    ``default`` AND a ``(default: X)`` clause AND that default resolves to one of
    its own choices. The last condition failing is reported, not skipped.
    """
    assertable, unassertable = [], []
    for group in vars(ClaudeCog).values():
        if not isinstance(group, discord.SlashCommandGroup):
            continue
        for subcommand in group.subcommands:
            for option in getattr(subcommand, "options", []):
                choices = getattr(option, "choices", None) or []
                actual = getattr(option, "default", None)
                if not choices or actual is None:
                    continue
                match = DEFAULT_CLAUSE_RE.search(getattr(option, "description", "") or "")
                if not match:
                    continue
                option_id = f"{group.name}.{subcommand.name}.{option.name}"
                claimed = match.group(1).strip()
                display_name = next((c.name for c in choices if c.value == actual), None)
                if display_name is None:
                    unassertable.append((option_id, claimed, actual))
                    continue
                assertable.append((option_id, claimed, actual, display_name))
    return assertable, unassertable


_ASSERTABLE_OPTIONS, _UNASSERTABLE_OPTIONS = _discover_defaulted_choice_options()

# The EXACT number of in-scope options discovery must find in this repo, not a
# floor. A ">= N" floor in a repo whose real count IS N is behaviourally
# identical to a bare non-emptiness check, so a PARTIAL discovery collapse — say
# py-cord changing where options hang off subcommands, leaving only some groups
# resolvable — could still satisfy it while the guard silently stopped covering
# most of the bot.
#
# NEXT CONTRIBUTOR: when you add or remove a choice-backed option that states a
# default, UPDATE these two numbers deliberately in the same commit. A mismatch
# means either a real change to the command surface or a discovery regression —
# both deserve a human look, which is the entire point of pinning them.
_EXPECTED_ASSERTABLE_OPTIONS = 2
_EXPECTED_UNASSERTABLE_OPTIONS = 0


def test_discovery_finds_exactly_the_known_options():
    """Fail loudly if discovery over- or under-reports (cog moved, py-cord changed)."""
    found = (len(_ASSERTABLE_OPTIONS), len(_UNASSERTABLE_OPTIONS))
    expected = (_EXPECTED_ASSERTABLE_OPTIONS, _EXPECTED_UNASSERTABLE_OPTIONS)
    assert found == expected, (
        f"Discovery found {found[0]} assertable and {found[1]} unassertable option(s); "
        f"this repo records {expected[0]} and {expected[1]}. Assertable: "
        f"{sorted(option_id for option_id, *_ in _ASSERTABLE_OPTIONS)}; unassertable: "
        f"{sorted(option_id for option_id, *_ in _UNASSERTABLE_OPTIONS)}. If you added or "
        "removed a choice-backed option with a stated default, update the recorded counts "
        "above in this commit. If you did not, discovery has regressed — did the cog or its "
        "command groups move, or did py-cord change how options hang off subcommands? Fix "
        "discovery; do not relax this assertion."
    )


def test_no_option_default_resolves_outside_its_own_choices():
    """Surface options whose default resolves to none of their own choices.

    That is a real bug, but a different one, and the per-option guard below
    cannot describe it accurately — so it is reported here rather than silently
    counted as a pass.
    """
    assert not _UNASSERTABLE_OPTIONS, (
        "These options state a default that resolves to NO choice of their own — the "
        "value cannot be selected from the picker at all, so either the default or the "
        f"choice list is wrong: {_UNASSERTABLE_OPTIONS}"
    )


@pytest.mark.parametrize(
    ("option_id", "claimed", "actual", "display_name"),
    _ASSERTABLE_OPTIONS,
    ids=[option_id for option_id, *_ in _ASSERTABLE_OPTIONS],
)
def test_option_description_names_its_real_default(option_id, claimed, actual, display_name):
    assert _description_names_default(display_name, actual, claimed), (
        f"{option_id} advertises '(default: {claimed})' but its default is "
        f"{actual!r}, which is the {display_name!r} choice. Discord shows that "
        "description verbatim in the command picker, so users are being told the "
        "wrong default. Update the option description to name the real default."
    )
