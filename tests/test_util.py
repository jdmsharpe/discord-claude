import hashlib
import hmac
import importlib
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import discord_claude
import discord_claude.config
import discord_claude.config.auth
import discord_claude.util
from discord_claude.util import (
    ADAPTIVE_ONLY_THINKING_MODELS,
    ADAPTIVE_THINKING_MODELS,
    ADVISOR_MODEL_COMPATIBILITY,
    CHUNK_TEXT_SIZE,
    COMPACTION_MODELS,
    COMPACTION_SUMMARY_MODEL,
    DISCORD_EMBED_TOTAL_LIMIT,
    EFFORT_MODELS,
    EXTENDED_THINKING_MODELS,
    FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS,
    MAX_EFFORT_MODELS,
    MODEL_CONTEXT_WINDOWS,
    PER_MESSAGE_EFFORT_MODELS,
    PROGRAMMATIC_TOOL_CALLING_UNSUPPORTED_MODELS,
    REFUSAL_FALLBACK_BETA,
    REFUSAL_FALLBACK_MODELS,
    REFUSAL_FALLBACK_TARGETS,
    SAFETY_IDENTIFIER_KEY_LABEL,
    SAMPLING_LOCKED_MODELS,
    THINKING_DISPLAY_UPDATES_MODELS,
    XHIGH_EFFORT_MODELS,
    ChatCompletionParameters,
    Conversation,
    ModelTokenUsage,
    UsageTotals,
    available_embed_space,
    build_safety_identifier,
    calculate_cost,
    chunk_text,
    derive_safety_identifier_key,
    format_anthropic_error,
    get_default_advisor_model,
    long_context_applies,
    priced_model,
    request_metadata,
    supported_effort_levels,
    truncate_text,
)


class TestChunkText:
    """Tests for the chunk_text function."""

    def test_short_text_single_chunk(self):
        """Short text should return a single chunk."""
        text = "Hello, world!"
        result = chunk_text(text)
        assert result == ["Hello, world!"]

    def test_exact_chunk_size(self):
        """Text exactly at chunk size should return one chunk."""
        text = "a" * CHUNK_TEXT_SIZE
        result = chunk_text(text)
        assert len(result) == 1
        assert result[0] == text

    def test_text_splits_into_multiple_chunks(self):
        """Text longer than chunk size should split into multiple chunks."""
        text = "a" * (CHUNK_TEXT_SIZE * 2 + 100)
        result = chunk_text(text)
        assert len(result) == 3
        assert len(result[0]) == CHUNK_TEXT_SIZE
        assert len(result[1]) == CHUNK_TEXT_SIZE
        assert len(result[2]) == 100

    def test_custom_chunk_size(self):
        """Custom chunk size should be respected."""
        text = "Hello, world! This is a test."
        result = chunk_text(text, chunk_size=10)
        assert len(result) == 3
        assert result[0] == "Hello, wor"
        assert result[1] == "ld! This i"
        assert result[2] == "s a test."

    def test_empty_string(self):
        """Empty string should return empty list."""
        result = chunk_text("")
        assert result == []


class TestTruncateText:
    """Tests for the truncate_text function."""

    def test_short_text_unchanged(self):
        """Text shorter than max_length should be unchanged."""
        text = "Hello"
        result = truncate_text(text, 10)
        assert result == "Hello"

    def test_exact_length_unchanged(self):
        """Text at exact max_length should be unchanged."""
        text = "Hello"
        result = truncate_text(text, 5)
        assert result == "Hello"

    def test_long_text_truncated(self):
        """Text longer than max_length should be truncated with suffix."""
        text = "Hello, world!"
        result = truncate_text(text, 8)
        assert result == "Hello, w..."

    def test_custom_suffix(self):
        """Custom suffix should be used."""
        text = "Hello, world!"
        result = truncate_text(text, 8, suffix="[cut]")
        assert result == "Hello, w[cut]"

    def test_none_returns_none(self):
        """None input should return None."""
        result = truncate_text(None, 10)
        assert result is None


class TestFormatAnthropicError:
    """Tests for the format_anthropic_error function."""

    def test_basic_exception(self):
        """Basic exception should format correctly."""
        error = Exception("Something went wrong")
        result = format_anthropic_error(error)
        assert "Something went wrong" in result

    def test_exception_with_status_code(self):
        """Exception with status_code attribute should include it."""
        error = Exception("API error")
        error.status_code = 429
        result = format_anthropic_error(error)
        assert "API error" in result
        assert "Status: 429" in result

    def test_exception_with_message_attribute(self):
        """Exception with message attribute should use it."""
        error = Exception()
        error.message = "Custom message"
        result = format_anthropic_error(error)
        assert "Custom message" in result


class TestChatCompletionParameters:
    """Tests for the ChatCompletionParameters dataclass."""

    def test_default_values(self):
        """Default values should be set correctly."""
        params = ChatCompletionParameters(model="claude-sonnet-4")
        assert params.model == "claude-sonnet-4"
        assert params.system is None
        assert params.temperature is None
        assert params.effort is None
        assert params.max_tokens == 16384
        assert params.paused is False
        assert params.tools == []
        assert params.mcp_preset_names == []
        assert params.advisor_model is None
        assert params.tool_choice is None

    def test_tools_isolation_between_instances(self):
        """Tools list should not be shared between instances."""
        params1 = ChatCompletionParameters(model="claude-sonnet-4")
        params2 = ChatCompletionParameters(model="claude-sonnet-4")
        params1.tools.append("web_search")
        assert params2.tools == []

    def test_mcp_preset_names_isolation_between_instances(self):
        params1 = ChatCompletionParameters(model="claude-sonnet-4")
        params2 = ChatCompletionParameters(model="claude-sonnet-4")
        params1.mcp_preset_names.append("github")
        assert params2.mcp_preset_names == []


class TestConversation:
    """Tests for the Conversation dataclass."""

    def test_conversation_creation(self):
        """Conversation should store params and messages."""
        params = ChatCompletionParameters(model="claude-sonnet-4")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        conv = Conversation(params=params, messages=messages)

        assert conv.params == params
        assert conv.messages == messages
        assert len(conv.messages) == 2


class TestCalculateCost:
    """Tests for the calculate_cost function."""

    def test_basic_cost(self):
        """Basic cost calculation with input and output tokens."""
        # claude-sonnet-4-6: $3/MTok input, $15/MTok output
        cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == 18.0  # $3 + $15

    def test_sonnet_5_pricing(self):
        """Sonnet 5 standard pricing: $2/MTok input, $10/MTok output.

        Launched as introductory pricing through 2026-08-31; Anthropic cancelled
        the scheduled 2026-09-01 increase to $3/$15 and made $2/$10 standard.
        """
        cost = calculate_cost("claude-sonnet-5", 1_000_000, 1_000_000)
        assert cost == pytest.approx(12.0)  # $2 + $10

    def test_zero_tokens(self):
        """Zero tokens should return zero cost."""
        cost = calculate_cost("claude-sonnet-4-6", 0, 0)
        assert cost == 0.0

    def test_cache_write_tokens(self):
        """Cache write tokens cost 2x base input price (1h TTL)."""
        # claude-sonnet-4-6: $3/MTok input, so cache write = $6/MTok
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, cache_creation_tokens=1_000_000)
        assert cost == 6.0

    def test_cache_read_tokens(self):
        """Cache read tokens cost 0.1x base input price."""
        # claude-sonnet-4-6: $3/MTok input, so cache read = $0.30/MTok
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, cache_read_tokens=1_000_000)
        assert cost == pytest.approx(0.30)

    def test_fable_5_1_cache_reads_bill_at_the_declared_quarter_rate(self):
        """Fable 5.1 cache reads are 0.025x input ($0.25/MTok), not the 0.1x default.

        The default multiplier would say $1.00; cache writes stay at 2x ($20/MTok) and
        the base $10/$50 rates match Fable 5.
        """
        read = calculate_cost("claude-fable-5-1", 0, 0, cache_read_tokens=1_000_000)
        assert read == pytest.approx(0.25)
        write = calculate_cost("claude-fable-5-1", 0, 0, cache_creation_tokens=1_000_000)
        assert write == pytest.approx(20.0)
        assert calculate_cost("claude-fable-5-1", 1_000_000, 1_000_000) == pytest.approx(60.0)
        # Every other model keeps the 0.1x default (Fable 5: $10 input -> $1.00 reads).
        fable_5 = calculate_cost("claude-fable-5", 0, 0, cache_read_tokens=1_000_000)
        assert fable_5 == pytest.approx(1.00)

    def test_all_token_types(self):
        """Cost with all token types combined."""
        cost = calculate_cost(
            "claude-sonnet-4-6",
            input_tokens=500_000,  # $1.50
            output_tokens=100_000,  # $1.50
            cache_creation_tokens=200_000,  # $1.20
            cache_read_tokens=1_000_000,  # $0.30
        )
        assert cost == pytest.approx(4.50)

    def test_opus_5_5_pricing(self):
        """Opus 5.5: $4/MTok input, $20/MTok output, cache reads $0.20/MTok (0.05x, not
        the 0.1x default), 1h cache writes $8/MTok (2x), 1M-token window."""
        assert calculate_cost("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
        assert calculate_cost("claude-opus-5-5", 0, 1_000_000) == pytest.approx(20.0)
        read = calculate_cost("claude-opus-5-5", 0, 0, cache_read_tokens=1_000_000)
        assert read == pytest.approx(0.20)
        write = calculate_cost("claude-opus-5-5", 0, 0, cache_creation_tokens=1_000_000)
        assert write == pytest.approx(8.0)
        assert MODEL_CONTEXT_WINDOWS.get("claude-opus-5-5") == 1_000_000

    def test_opus_5_pricing(self):
        """Opus 5 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-5", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_opus_4_6_pricing(self):
        """Opus 4.6 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-4-6", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_opus_4_7_pricing(self):
        """Opus 4.7 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-4-7", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_opus_4_5_pricing(self):
        """Opus 4.5 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-4-5", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_opus_4_1_pricing(self):
        """Opus 4.1 uses $15/MTok input, $75/MTok output."""
        cost = calculate_cost("claude-opus-4-1", 1_000_000, 1_000_000)
        assert cost == 90.0  # $15 + $75

    def test_haiku_4_5_pricing(self):
        """Haiku 4.5 uses $1/MTok input, $5/MTok output."""
        cost = calculate_cost("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert cost == 6.0  # $1 + $5

    def test_web_search_cost(self):
        """Web search requests cost $0.01 each."""
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, web_search_requests=1)
        assert cost == pytest.approx(0.01)

    def test_web_search_cost_multiple(self):
        """Multiple web search requests accumulate."""
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, web_search_requests=5)
        assert cost == pytest.approx(0.05)

    def test_web_search_with_tokens(self):
        """Web search cost combines with token costs."""
        cost = calculate_cost(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,  # $3.00
            output_tokens=100_000,  # $1.50
            web_search_requests=3,  # $0.03
        )
        assert cost == pytest.approx(4.53)

    def test_unknown_model_uses_default(self):
        """Unknown model should use default pricing."""
        cost = calculate_cost("unknown-model", 1_000_000, 0)
        assert cost == 15.0  # Default input price

    def test_sonnet_5_5_pricing(self):
        """Sonnet 5.5: $2 / $10, cache reads $0.10 (0.05x), 1h cache writes $4 (2x)."""
        assert calculate_cost("claude-sonnet-5-5", 1_000_000, 0) == pytest.approx(2.0)
        assert calculate_cost("claude-sonnet-5-5", 0, 1_000_000) == pytest.approx(10.0)
        read = calculate_cost("claude-sonnet-5-5", 0, 0, cache_read_tokens=1_000_000)
        assert read == pytest.approx(0.10)
        write = calculate_cost("claude-sonnet-5-5", 0, 0, cache_creation_tokens=1_000_000)
        assert write == pytest.approx(4.0)
        # Sonnet 5 lists the same $2 / $10 but reads at the default 0.1x.
        sonnet_5_read = calculate_cost("claude-sonnet-5", 0, 0, cache_read_tokens=1_000_000)
        assert sonnet_5_read == pytest.approx(0.20)

    def test_haiku_5_5_pricing_tiers(self):
        """Haiku 5.5, prompts up to 100,000 tokens: $0.10 / $0.50, cache reads $0.01, 1h
        cache writes $0.20. Prompts over 100,000 tokens: $0.50 / $2.50, $0.05, $1.00."""
        model = "claude-haiku-5-5"
        for long_context, expected in (
            (False, (0.10, 0.50, 0.01, 0.20)),
            (True, (0.50, 2.50, 0.05, 1.00)),
        ):
            assert calculate_cost(model, 1_000_000, 0, long_context=long_context) == pytest.approx(
                expected[0]
            )
            assert calculate_cost(model, 0, 1_000_000, long_context=long_context) == pytest.approx(
                expected[1]
            )
            assert calculate_cost(
                model, 0, 0, cache_read_tokens=1_000_000, long_context=long_context
            ) == pytest.approx(expected[2])
            assert calculate_cost(
                model, 0, 0, cache_creation_tokens=1_000_000, long_context=long_context
            ) == pytest.approx(expected[3])

    def test_long_context_flag_has_no_effect_without_a_tier(self):
        assert calculate_cost(
            "claude-opus-5-5", 1_000_000, 1_000_000, long_context=True
        ) == pytest.approx(calculate_cost("claude-opus-5-5", 1_000_000, 1_000_000))

    def test_long_context_applies_above_100_000_prompt_tokens(self):
        """The higher prices apply to prompts OVER 100,000 tokens."""
        assert long_context_applies("claude-haiku-5-5", 100_000) is False
        assert long_context_applies("claude-haiku-5-5", 100_001) is True
        assert long_context_applies("claude-haiku-5-5", 900_000) is True
        assert long_context_applies("claude-opus-5-5", 900_000) is False
        assert long_context_applies("unknown-model", 900_000) is False

    def test_priced_model_resolves_ids_without_a_pricing_row_to_the_request_model(self):
        """Usage entries bill at the named model's row when it has one; None and ids
        without a row (such as a dated snapshot id) use the request model's row
        instead of the $15/$75 unknown-model fallback."""
        assert priced_model("claude-opus-4-8", "claude-opus-5-5") == "claude-opus-4-8"
        assert priced_model(None, "claude-opus-5-5") == "claude-opus-5-5"
        assert priced_model("claude-haiku-4-5-20251001", "claude-haiku-4-5") == "claude-haiku-4-5"

    def test_opus_4_7_context_window(self):
        """Opus 4.7 uses the 1M token context window."""
        assert MODEL_CONTEXT_WINDOWS["claude-opus-4-7"] == 1_000_000

    def test_opus_5_context_window(self):
        """Opus 5 ships the 1M token context window with no beta header."""
        assert MODEL_CONTEXT_WINDOWS["claude-opus-5"] == 1_000_000


class TestModelCapabilitySets:
    """Guards for the per-model capability sets consumed by build_api_params."""

    def test_manual_compaction_trigger_bounded_by_summarizer(self):
        """A manual-path model must not out-scale the summarizer.

        compact_conversation hands the whole message list to
        COMPACTION_SUMMARY_MODEL, so an unbounded 75% trigger on a model with a
        larger window than the summarizer's would send it a prompt it rejects. No
        selectable manual-path model has a window larger than the summarizer's
        (Haiku 5.5, 1M), so this pins the guard rather than a live bound.

        Resolved with .get() and the same 200_000 default the production code
        uses: the pricing-override tests replace MODEL_CONTEXT_WINDOWS globally,
        so indexing it directly makes this test order-dependent.
        """
        from discord_claude.util import (
            COMPACTION_SUMMARY_MODEL,
            MODEL_CONTEXT_WINDOWS,
            manual_compaction_trigger,
        )

        summary_window = MODEL_CONTEXT_WINDOWS.get(COMPACTION_SUMMARY_MODEL, 200_000)

        # A window larger than the summarizer's is bounded by the summarizer.
        assert manual_compaction_trigger(summary_window * 2) == summary_window * 0.75
        assert manual_compaction_trigger(summary_window * 2) < summary_window

        # A window at or below the summarizer's is unaffected.
        assert manual_compaction_trigger(200_000) == 200_000 * 0.75
        assert manual_compaction_trigger(100_000) == 100_000 * 0.75

    def test_compaction_summary_model_is_haiku_5_5(self):
        """The summarizer is Haiku 5.5: priced with its long-context tier and never sent
        `fallbacks` (it rejects the parameter). Haiku 4.5 stays a chat model."""
        from pathlib import Path

        import yaml

        from discord_claude.cogs.claude.command_options import CHAT_MODEL_CHOICES
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, REFUSAL_FALLBACK_MODELS

        # Read the bundled YAML directly: the CLAUDE_PRICING_PATH override tests
        # re-import the pricing module.
        bundled = yaml.safe_load(
            (
                Path(__file__).parent.parent / "src" / "discord_claude" / "config" / "pricing.yaml"
            ).read_text()
        )
        assert COMPACTION_SUMMARY_MODEL == "claude-haiku-5-5"
        assert COMPACTION_SUMMARY_MODEL not in REFUSAL_FALLBACK_MODELS
        assert bundled["models"][COMPACTION_SUMMARY_MODEL]["long_context"]["threshold_tokens"] == (
            100_001
        )
        assert "claude-haiku-4-5" in {choice.value for choice in CHAT_MODEL_CHOICES}

    def test_opus_5_takes_the_server_side_compaction_path(self):
        """Opus 5 is 1M-window and server-side compacted, so the bound above never applies to it.

        The remaining manual-path choices are all 200k-window models, so the
        summarizer bound in manual_compaction_trigger is currently a guard rather
        than a live limit; both halves are pinned here so they cannot drift apart
        silently (compaction docs verified 2026-08-28).
        """
        from pathlib import Path

        import yaml

        from discord_claude.cogs.claude.command_options import CHAT_MODEL_CHOICES
        from discord_claude.util import COMPACTION_MODELS, COMPACTION_SUMMARY_MODEL

        # Read the bundled YAML directly: the module-level dicts can be replaced
        # by the CLAUDE_PRICING_PATH override tests.
        bundled = yaml.safe_load(
            (
                Path(__file__).parent.parent / "src" / "discord_claude" / "config" / "pricing.yaml"
            ).read_text()
        )
        assert bundled["models"]["claude-opus-5"]["context_window"] == 1_000_000
        assert "claude-opus-5" in COMPACTION_MODELS

        manual_path = {choice.value for choice in CHAT_MODEL_CHOICES} - COMPACTION_MODELS
        assert manual_path == {"claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"}
        summary_window = bundled["models"][COMPACTION_SUMMARY_MODEL]["context_window"]
        for model_id in manual_path:
            assert bundled["models"][model_id]["context_window"] <= summary_window, model_id

    def test_advisor_model_compatibility_matches_accepted_pairs(self):
        """Pins the executor -> advisor pairs the API accepts. The advisor-tool docs table
        lists exactly these pairs, and beta.messages.count_tokens with the bot's advisor
        tool accepted every one of them and rejected every other pair of selectable
        models (see .claude/CLAUDE.md, Advisor pairs).

        Tuple order matters: get_default_advisor_model takes the first entry, so
        claude-opus-4-8 leads wherever it is allowed (plaintext advice), the Opus 5 /
        Fable 5 executors default to claude-opus-5 (encrypted advisor_redacted_result),
        the Opus 5.5 executor to claude-opus-5-5 and the Sonnet 5.5 executor to
        claude-sonnet-5-5. New advisors are appended, so adding claude-sonnet-5-5 and
        claude-haiku-5-5 changed no tuple's first entry. claude-mythos-5 /
        claude-mythos-5-1 are in the docs table but not publicly callable;
        claude-sonnet-4-5 and claude-opus-4-5 are not executors.
        """
        assert ADVISOR_MODEL_COMPATIBILITY == {
            "claude-haiku-4-5": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5",
                "claude-sonnet-4-6",
                "claude-sonnet-5-5",
                "claude-haiku-5-5",
            ),
            "claude-haiku-5-5": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5",
                "claude-sonnet-5-5",
                "claude-haiku-5-5",
            ),
            "claude-sonnet-4-6": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5",
                "claude-sonnet-4-6",
                "claude-sonnet-5-5",
                "claude-haiku-5-5",
            ),
            "claude-sonnet-5": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5",
                "claude-sonnet-5-5",
                "claude-haiku-5-5",
            ),
            "claude-sonnet-5-5": (
                "claude-sonnet-5-5",
                "claude-opus-5-5",
                "claude-opus-5",
                "claude-fable-5",
                "claude-fable-5-1",
            ),
            "claude-opus-4-6": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5",
                "claude-sonnet-5-5",
                "claude-haiku-5-5",
            ),
            "claude-opus-4-7": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5-5",
            ),
            "claude-opus-4-8": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
                "claude-sonnet-5-5",
            ),
            "claude-opus-5-5": (
                "claude-opus-5-5",
                "claude-opus-5",
                "claude-fable-5",
                "claude-fable-5-1",
            ),
            "claude-opus-5": (
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
            ),
            "claude-fable-5": (
                "claude-opus-5",
                "claude-opus-5-5",
                "claude-fable-5",
                "claude-fable-5-1",
            ),
            "claude-fable-5-1": ("claude-fable-5-1",),
        }
        for mythos in ("claude-mythos-5", "claude-mythos-5-1"):
            assert mythos not in ADVISOR_MODEL_COMPATIBILITY
            for advisors in ADVISOR_MODEL_COMPATIBILITY.values():
                assert mythos not in advisors
        # The API rejects Opus 4.8 as the advisor of an Opus 5.5 or Sonnet 5.5 executor,
        # and Haiku 5.5 as the advisor of an Opus 4.7 / 4.8 executor.
        assert "claude-opus-4-8" not in ADVISOR_MODEL_COMPATIBILITY["claude-opus-5-5"]
        assert "claude-opus-4-8" not in ADVISOR_MODEL_COMPATIBILITY["claude-sonnet-5-5"]
        for executor in ("claude-opus-4-7", "claude-opus-4-8"):
            assert "claude-haiku-5-5" not in ADVISOR_MODEL_COMPATIBILITY[executor], executor
        # Haiku 4.5 is never an advisor.
        for advisors in ADVISOR_MODEL_COMPATIBILITY.values():
            assert "claude-haiku-4-5" not in advisors

    def test_default_advisor_model_prefers_plaintext_opus_4_8(self):
        """The auto-picked advisor is Opus 4.8 wherever the API allows it.

        Only Opus 5 / Fable 5 executors fall through to claude-opus-5, the Opus 5.5
        executor to claude-opus-5-5 and the Sonnet 5.5 executor to claude-sonnet-5-5;
        models outside the table (Sonnet 4.5, Opus 4.5) get
        no advisor at all.
        """
        for executor in (
            "claude-haiku-4-5",
            "claude-haiku-5-5",
            "claude-sonnet-4-6",
            "claude-sonnet-5",
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-opus-4-8",
        ):
            assert get_default_advisor_model(executor) == "claude-opus-4-8", executor
        for executor in ("claude-opus-5", "claude-fable-5"):
            assert get_default_advisor_model(executor) == "claude-opus-5", executor
        assert get_default_advisor_model("claude-opus-5-5") == "claude-opus-5-5"
        assert get_default_advisor_model("claude-sonnet-5-5") == "claude-sonnet-5-5"
        assert get_default_advisor_model("claude-fable-5-1") == "claude-fable-5-1"
        for executor in ("claude-sonnet-4-5", "claude-opus-4-5"):
            assert get_default_advisor_model(executor) is None, executor

    def test_opus_5_capability_membership(self):
        """Opus 5 is adaptive-thinking-only and sampling-locked.

        Manual thinking with budget_tokens returns a 400, so it must stay out of
        EXTENDED_THINKING_MODELS.
        """
        assert "claude-opus-5" in ADAPTIVE_THINKING_MODELS
        assert "claude-opus-5" in ADAPTIVE_ONLY_THINKING_MODELS
        assert "claude-opus-5" in SAMPLING_LOCKED_MODELS
        assert "claude-opus-5" not in EXTENDED_THINKING_MODELS

    def test_fable_5_1_capability_membership(self):
        """Fable 5.1 (GA 2026-09-01) mirrors Fable 5 — adaptive-only, sampling-locked,
        server-side compaction, refusal classifiers — and is the first model that 400s
        on forced tool use (live-probed 2026-09-03)."""
        assert "claude-fable-5-1" in ADAPTIVE_THINKING_MODELS
        assert "claude-fable-5-1" in ADAPTIVE_ONLY_THINKING_MODELS
        assert "claude-fable-5-1" in SAMPLING_LOCKED_MODELS
        assert "claude-fable-5-1" in COMPACTION_MODELS
        assert "claude-fable-5-1" in REFUSAL_FALLBACK_MODELS
        assert "claude-fable-5-1" not in EXTENDED_THINKING_MODELS
        assert "claude-fable-5-1" in FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS

    def test_opus_5_5_capability_membership(self):
        """Opus 5.5: adaptive thinking only (enabled and disabled both 400), sampling-locked,
        all five effort levels, per-message effort, thinking display `updates`, server-side
        compaction, refusal classifiers, and a 400 on forced tool use. It supports
        programmatic tool calling, and the API accepts it as an executor with the advisor
        tool and as the advisor of every executor, although the advisor docs table lists
        neither."""
        model = "claude-opus-5-5"
        for member_of in (
            ADAPTIVE_THINKING_MODELS,
            ADAPTIVE_ONLY_THINKING_MODELS,
            SAMPLING_LOCKED_MODELS,
            FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS,
            THINKING_DISPLAY_UPDATES_MODELS,
            PER_MESSAGE_EFFORT_MODELS,
            EFFORT_MODELS,
            XHIGH_EFFORT_MODELS,
            MAX_EFFORT_MODELS,
            COMPACTION_MODELS,
            REFUSAL_FALLBACK_MODELS,
        ):
            assert model in member_of
        assert model not in EXTENDED_THINKING_MODELS
        assert model not in PROGRAMMATIC_TOOL_CALLING_UNSUPPORTED_MODELS
        for executor, advisors in ADVISOR_MODEL_COMPATIBILITY.items():
            if executor == "claude-fable-5-1":
                # The API rejects an Opus 5.5 advisor for a Fable 5.1 executor.
                assert model not in advisors
            else:
                assert model in advisors, executor
        assert get_default_advisor_model(model) == model
        assert supported_effort_levels(model) == {"low", "medium", "high", "xhigh", "max"}
        assert {
            "claude-fable-5-1",
            "claude-opus-5-5",
            "claude-sonnet-5-5",
        } == FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS

    @pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5"])
    def test_5_5_models_capability_membership(self, model):
        """Sonnet 5.5 and Haiku 5.5: adaptive thinking only (budget_tokens 400s),
        sampling-locked, all five effort levels, per-message effort, server-side
        compaction and programmatic tool calling with the default allowed_callers.
        Both must be in ADAPTIVE_THINKING_MODELS: otherwise no thinking config is sent
        and their default display "omitted" hides the reasoning."""
        for member_of in (
            ADAPTIVE_THINKING_MODELS,
            ADAPTIVE_ONLY_THINKING_MODELS,
            SAMPLING_LOCKED_MODELS,
            PER_MESSAGE_EFFORT_MODELS,
            EFFORT_MODELS,
            XHIGH_EFFORT_MODELS,
            MAX_EFFORT_MODELS,
            COMPACTION_MODELS,
        ):
            assert model in member_of
        assert model not in EXTENDED_THINKING_MODELS
        assert model not in PROGRAMMATIC_TOOL_CALLING_UNSUPPORTED_MODELS
        assert supported_effort_levels(model) == {"low", "medium", "high", "xhigh", "max"}

    def test_sonnet_5_5_only_capabilities(self):
        """Sonnet 5.5 writes progress updates between tool calls, 400s on forced tool use
        and falls back to Sonnet 5 on a refusal. Haiku 5.5 does none of these: it writes
        no progress updates, accepts forced tool use and rejects `fallbacks`."""
        assert "claude-sonnet-5-5" in THINKING_DISPLAY_UPDATES_MODELS
        assert "claude-sonnet-5-5" in FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS
        assert REFUSAL_FALLBACK_TARGETS["claude-sonnet-5-5"] == "claude-sonnet-5"
        assert "claude-haiku-5-5" not in THINKING_DISPLAY_UPDATES_MODELS
        assert "claude-haiku-5-5" not in FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS
        assert "claude-haiku-5-5" not in REFUSAL_FALLBACK_MODELS

    def test_retired_opus_4_1_absent_from_capability_sets(self):
        """Opus 4.1 shut down 2026-08-05; its thinking config is dead once unselectable."""
        assert "claude-opus-4-1" not in EXTENDED_THINKING_MODELS

    def test_refusal_fallback_models_are_the_classifier_models(self):
        """Anthropic's refusals page names Fable 5 and Opus 5 as the models with safety
        classifiers, and the Fable 5.1, Opus 5.5 and Sonnet 5.5 model pages add those
        models. Each maps to a target the API permits for it: Opus 4.8 (no classifier)
        for the Fable / Opus models, Sonnet 5 for Sonnet 5.5, which rejects Opus 4.8.
        Haiku 5.5 has classifiers but rejects the `fallbacks` parameter, so it is not
        listed."""
        assert REFUSAL_FALLBACK_TARGETS == {
            "claude-fable-5-1": "claude-opus-4-8",
            "claude-fable-5": "claude-opus-4-8",
            "claude-opus-5-5": "claude-opus-4-8",
            "claude-opus-5": "claude-opus-4-8",
            "claude-sonnet-5-5": "claude-sonnet-5",
        }
        assert frozenset(REFUSAL_FALLBACK_TARGETS) == REFUSAL_FALLBACK_MODELS
        for target in REFUSAL_FALLBACK_TARGETS.values():
            assert target not in REFUSAL_FALLBACK_MODELS, target
        assert "claude-haiku-5-5" not in REFUSAL_FALLBACK_MODELS
        assert REFUSAL_FALLBACK_BETA == "server-side-fallback-2026-06-01"

    def test_effort_model_sets_membership(self):
        """Pins the per-model effort gate (live-probed 2026-08-28).

        Sonnet 4.5 / Haiku 4.5 reject the parameter, Opus 4.5 stops at high,
        the 4.6 pair adds max but not xhigh, everything newer takes all five.
        """
        assert {
            "claude-fable-5-1",
            "claude-fable-5",
            "claude-opus-5-5",
            "claude-opus-5",
            "claude-sonnet-5-5",
            "claude-sonnet-5",
            "claude-haiku-5-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-opus-4-5",
        } == EFFORT_MODELS
        assert {
            "claude-fable-5-1",
            "claude-fable-5",
            "claude-opus-5-5",
            "claude-opus-5",
            "claude-sonnet-5-5",
            "claude-sonnet-5",
            "claude-haiku-5-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
        } == XHIGH_EFFORT_MODELS
        assert XHIGH_EFFORT_MODELS | {"claude-opus-4-6", "claude-sonnet-4-6"} == MAX_EFFORT_MODELS
        assert XHIGH_EFFORT_MODELS <= MAX_EFFORT_MODELS <= EFFORT_MODELS
        assert "claude-sonnet-4-5" not in EFFORT_MODELS
        assert "claude-haiku-4-5" not in EFFORT_MODELS

    def test_every_chat_model_choice_has_an_effort_classification(self):
        """Every selectable model resolves to a known effort ladder.

        A new CHAT_MODEL_CHOICES id must be added to this table so its gate is
        a deliberate decision rather than a silent empty set.
        """
        from discord_claude.cogs.claude.command_options import CHAT_MODEL_CHOICES

        expected = {
            "claude-fable-5-1": {"low", "medium", "high", "xhigh", "max"},
            "claude-fable-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-5-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-4-8": {"low", "medium", "high", "xhigh", "max"},
            "claude-sonnet-5-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-sonnet-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-4-7": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-4-6": {"low", "medium", "high", "max"},
            "claude-sonnet-4-6": {"low", "medium", "high", "max"},
            "claude-opus-4-5": {"low", "medium", "high"},
            "claude-sonnet-4-5": set(),
            "claude-haiku-5-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-haiku-4-5": set(),
        }
        choice_ids = {choice.value for choice in CHAT_MODEL_CHOICES}
        assert choice_ids == set(expected)
        for model_id, levels in expected.items():
            assert supported_effort_levels(model_id) == levels, model_id


class TestUsageTotals:
    """Tests for the UsageTotals dataclass."""

    def test_accumulate_basic(self):
        """Basic token accumulation from a usage object."""
        totals = UsageTotals()
        usage = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=20,
            server_tool_use=None,
        )
        totals.accumulate(usage)
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.cache_creation_tokens == 10
        assert totals.cache_read_tokens == 20

    def test_accumulate_multiple(self):
        """Multiple accumulations add up."""
        totals = UsageTotals()
        usage1 = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
        )
        usage2 = MagicMock(
            input_tokens=200,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
        )
        totals.accumulate(usage1)
        totals.accumulate(usage2)
        assert totals.input_tokens == 300
        assert totals.output_tokens == 150

    def test_accumulate_thinking_tokens(self):
        """thinking_tokens from usage.output_tokens_details are tracked (anthropic 0.105+)."""
        totals = UsageTotals()
        usage = MagicMock(
            input_tokens=100,
            output_tokens=80,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
            output_tokens_details=MagicMock(thinking_tokens=60),
        )
        totals.accumulate(usage)
        assert totals.output_tokens == 80
        assert totals.thinking_tokens == 60

    def test_accumulate_thinking_tokens_absent(self):
        """A None output_tokens_details leaves thinking_tokens at zero."""
        totals = UsageTotals()
        usage = MagicMock(
            input_tokens=100,
            output_tokens=80,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
            output_tokens_details=None,
        )
        totals.accumulate(usage)
        assert totals.thinking_tokens == 0

    def test_accumulate_thinking_tokens_with_iterations(self):
        """With usage.iterations present, thinking_tokens are read from the top-level
        output_tokens_details, because the iteration entries do not carry them."""
        totals = UsageTotals()
        usage = MagicMock(
            iterations=[
                MagicMock(
                    type="message",
                    model=None,
                    input_tokens=100,
                    output_tokens=40,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
                MagicMock(
                    type="message",
                    model=None,
                    input_tokens=150,
                    output_tokens=60,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
            ],
            output_tokens=100,
            output_tokens_details=MagicMock(thinking_tokens=70),
            server_tool_use=None,
        )
        totals.accumulate(usage)
        assert totals.output_tokens == 100
        assert totals.thinking_tokens == 70

    def test_accumulate_none_is_noop(self):
        """Accumulating None usage should not change totals."""
        totals = UsageTotals()
        totals.accumulate(None)
        assert totals.input_tokens == 0

    def test_accumulate_server_tool_use(self):
        """Server tool use counts are accumulated."""
        totals = UsageTotals()
        server_tool_use = MagicMock(
            web_search_requests=2,
            web_fetch_requests=1,
            code_execution_requests=0,
        )
        usage = MagicMock(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=server_tool_use,
        )
        totals.accumulate(usage)
        assert totals.web_search_requests == 2
        assert totals.web_fetch_requests == 1
        assert totals.code_execution_requests == 0

    def test_accumulate_advisor_iterations(self):
        """Advisor iterations are billed separately from executor iterations."""
        totals = UsageTotals()
        usage = MagicMock(
            iterations=[
                MagicMock(
                    type="message",
                    input_tokens=120,
                    output_tokens=40,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=10,
                ),
                MagicMock(
                    type="advisor_message",
                    input_tokens=300,
                    output_tokens=700,
                    cache_creation_input_tokens=50,
                    cache_read_input_tokens=25,
                ),
                MagicMock(
                    type="message",
                    input_tokens=80,
                    output_tokens=60,
                    cache_creation_input_tokens=5,
                    cache_read_input_tokens=0,
                ),
            ],
            server_tool_use=None,
        )

        totals.accumulate(usage)

        assert totals.input_tokens == 200
        assert totals.output_tokens == 100
        assert totals.cache_creation_tokens == 5
        assert totals.cache_read_tokens == 10
        assert totals.advisor_calls == 1
        assert totals.advisor_input_tokens == 300
        assert totals.advisor_output_tokens == 700
        assert totals.advisor_cache_creation_tokens == 50
        assert totals.advisor_cache_read_tokens == 25

    def test_accumulate_fallback_message_iterations(self):
        """A refusal-fallback turn's entries are grouped under the model each one names:
        the declined model's "message" attempt and the fallback model's
        "fallback_message" answer bill at different rates."""
        totals = UsageTotals()
        usage = MagicMock(
            iterations=[
                # The requested model's attempt, which declined.
                MagicMock(
                    type="message",
                    model="claude-opus-5-5",
                    input_tokens=140,
                    output_tokens=12,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
                # The attempt served by the fallback model.
                MagicMock(
                    type="fallback_message",
                    model="claude-opus-4-8",
                    input_tokens=150,
                    output_tokens=90,
                    cache_creation_input_tokens=20,
                    cache_read_input_tokens=30,
                ),
            ],
            server_tool_use=None,
        )

        totals.accumulate(usage)

        assert totals.input_tokens == 290
        assert totals.output_tokens == 102
        assert totals.cache_creation_tokens == 20
        assert totals.cache_read_tokens == 30
        assert totals.advisor_calls == 0
        assert totals.tokens_by_model == {
            "claude-opus-5-5": ModelTokenUsage(140, 12, 0, 0),
            "claude-opus-4-8": ModelTokenUsage(150, 90, 20, 30),
        }
        # The serving entry is the last one, so it gives the prompt size.
        assert totals.prompt_tokens == 150 + 20 + 30

    def test_accumulate_groups_entries_without_a_model_under_the_request_model(self):
        """Top-level usage, compaction entries and entries that name no model share the
        None key, which track_daily_cost bills at the request model's rates."""
        totals = UsageTotals()
        totals.accumulate(
            MagicMock(
                input_tokens=100,
                output_tokens=50,
                cache_creation_input_tokens=10,
                cache_read_input_tokens=20,
                server_tool_use=None,
            )
        )
        totals.accumulate(
            MagicMock(
                iterations=[
                    MagicMock(
                        type="compaction",
                        input_tokens=1_000,
                        output_tokens=200,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                    MagicMock(
                        type="message",
                        model=None,
                        input_tokens=30,
                        output_tokens=5,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                ],
                server_tool_use=None,
            )
        )

        assert totals.tokens_by_model == {None: ModelTokenUsage(1_130, 255, 10, 20)}

    def test_price_tier_is_chosen_per_entry_from_its_own_prompt(self):
        """Each sampling entry is a separate request: two 60,000-token Haiku 5.5 prompts
        stay at the standard prices although they add up past 100,000, while a
        compaction entry whose own prompt is over 100,000 tokens (cache reads included)
        goes to the long-context group. Entries that name no model resolve through
        request_model."""
        totals = UsageTotals(request_model="claude-haiku-5-5")
        totals.accumulate(
            MagicMock(
                iterations=[
                    MagicMock(
                        type="message",
                        model="claude-haiku-5-5",
                        input_tokens=60_000,
                        output_tokens=100,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                    MagicMock(
                        type="compaction",
                        input_tokens=1_000,
                        output_tokens=300,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=100_000,
                    ),
                    MagicMock(
                        type="message",
                        model="claude-haiku-5-5",
                        input_tokens=60_000,
                        output_tokens=200,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                ],
                server_tool_use=None,
            )
        )

        assert totals.tokens_by_model == {"claude-haiku-5-5": ModelTokenUsage(120_000, 300, 0, 0)}
        assert totals.long_context_tokens_by_model == {
            None: ModelTokenUsage(1_000, 300, 0, 100_000)
        }
        assert totals.input_tokens == 121_000

    def test_price_tier_boundary_is_inclusive_of_100_001(self):
        """A prompt of exactly 100,000 tokens bills at the standard prices; 100,001 does
        not. Without request_model, usage that names no model cannot be tiered."""
        at_threshold = MagicMock(
            input_tokens=100_000,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
        )
        over_threshold = MagicMock(
            input_tokens=99_000,
            output_tokens=0,
            cache_creation_input_tokens=1,
            cache_read_input_tokens=1_000,
            server_tool_use=None,
        )
        totals = UsageTotals(request_model="claude-haiku-5-5")
        totals.accumulate(at_threshold)
        totals.accumulate(over_threshold)
        assert totals.tokens_by_model == {None: ModelTokenUsage(100_000, 0, 0, 0)}
        assert totals.long_context_tokens_by_model == {None: ModelTokenUsage(99_000, 0, 1, 1_000)}

        untiered = UsageTotals()
        untiered.accumulate(over_threshold)
        assert untiered.long_context_tokens_by_model == {}

    def test_apply_to_stamps_the_long_context_group_and_compaction_failure(self):
        from discord_claude.cogs.claude.responses import ParsedResponse

        totals = UsageTotals(
            compaction_failed=True,
            long_context_tokens_by_model={None: ModelTokenUsage(200_000, 10, 0, 0)},
        )
        parsed = ParsedResponse()
        totals.apply_to(parsed, 1_000_000)

        assert parsed.compaction_failed is True
        assert parsed.long_context_tokens_by_model == {None: ModelTokenUsage(200_000, 10, 0, 0)}
        assert (
            parsed.long_context_tokens_by_model[None]
            is not totals.long_context_tokens_by_model[None]
        )

    def test_prompt_tokens_is_the_full_prompt_of_the_latest_response(self):
        """prompt_tokens counts uncached, cache-read and cache-write input tokens of the
        most recent response only (not a running sum), and a compaction entry, which
        reports the summarisation call, does not set it."""
        totals = UsageTotals()
        totals.accumulate(
            MagicMock(
                input_tokens=4_000,
                output_tokens=100,
                cache_creation_input_tokens=1_000,
                cache_read_input_tokens=120_000,
                server_tool_use=None,
            )
        )
        assert totals.prompt_tokens == 125_000

        totals.accumulate(
            MagicMock(
                iterations=[
                    MagicMock(
                        type="compaction",
                        input_tokens=150_000,
                        output_tokens=3_000,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                    MagicMock(
                        type="message",
                        input_tokens=500,
                        output_tokens=100,
                        cache_creation_input_tokens=3_000,
                        cache_read_input_tokens=0,
                    ),
                ],
                server_tool_use=None,
            )
        )
        assert totals.prompt_tokens == 3_500

    def test_accumulate_compaction_summary_bills_at_the_summary_model(self):
        """A manual compaction's summarizer call is grouped under COMPACTION_SUMMARY_MODEL
        and leaves prompt_tokens unchanged. Its 158k-token prompt is over Haiku 5.5's
        100,000-token threshold, so it goes in the long-context group."""
        totals = UsageTotals(prompt_tokens=160_000)
        totals.accumulate_compaction_summary(
            MagicMock(
                input_tokens=158_000,
                output_tokens=1_500,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
                output_tokens_details=None,
            )
        )
        totals.accumulate_compaction_summary(None)

        assert totals.tokens_by_model == {}
        assert totals.long_context_tokens_by_model == {
            COMPACTION_SUMMARY_MODEL: ModelTokenUsage(158_000, 1_500, 0, 0)
        }
        assert totals.input_tokens == 158_000
        assert totals.output_tokens == 1_500
        assert totals.prompt_tokens == 160_000

    def test_accumulate_compaction_iterations(self):
        """compaction iterations (server-side compact_20260112) bill at the executor's
        rates: the top-level counts exclude them, so they are summed from
        usage.iterations like every other executor entry, and the compaction embed
        is shown."""
        totals = UsageTotals()
        usage = MagicMock(
            iterations=[
                MagicMock(
                    type="compaction",
                    input_tokens=180_000,
                    output_tokens=3_500,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=150_000,
                ),
                MagicMock(
                    type="message",
                    input_tokens=4_000,
                    output_tokens=300,
                    cache_creation_input_tokens=3_500,
                    cache_read_input_tokens=0,
                ),
            ],
            server_tool_use=None,
        )

        totals.accumulate(usage)

        assert totals.input_tokens == 184_000
        assert totals.output_tokens == 3_800
        assert totals.cache_creation_tokens == 3_500
        assert totals.cache_read_tokens == 150_000
        assert totals.context_compacted is True
        assert totals.advisor_calls == 0

    def test_apply_to_sets_all_fields(self):
        """apply_to stamps all fields onto a target object."""
        totals = UsageTotals(
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=10,
            cache_read_tokens=20,
            web_search_requests=1,
            web_fetch_requests=2,
            code_execution_requests=3,
            context_compacted=True,
        )
        target = MagicMock()
        totals.apply_to(target, context_window=200_000)
        assert target.input_tokens == 100
        assert target.output_tokens == 50
        assert target.context_compacted is True
        assert target.context_warning is False  # 100 < 200_000 * 0.85
        assert target.advisor_calls == 0

    def test_apply_to_context_warning(self):
        """context_warning is True when the latest prompt exceeds 85% of the window,
        whether or not its tokens were read from the cache."""
        totals = UsageTotals(prompt_tokens=175_000)
        target = MagicMock()
        totals.apply_to(target, context_window=200_000)
        assert target.context_warning is True

        # Uncached input alone is not the measure.
        totals = UsageTotals(input_tokens=175_000, prompt_tokens=20_000)
        totals.apply_to(target, context_window=200_000)
        assert target.context_warning is False


class TestAvailableEmbedSpace:
    """Tests for the available_embed_space helper."""

    def test_empty_embeds(self):
        """No embeds should return full limit."""
        assert available_embed_space([]) == DISCORD_EMBED_TOTAL_LIMIT

    def test_with_reserve(self):
        """Reserve should be subtracted."""
        assert available_embed_space([], reserve=500) == DISCORD_EMBED_TOTAL_LIMIT - 500

    def test_with_existing_embeds(self):
        """Existing embed content reduces available space."""
        embed = MagicMock()
        embed.description = "a" * 1000
        embed.title = "Title"
        space = available_embed_space([embed])
        assert space == DISCORD_EMBED_TOTAL_LIMIT - 1005


class TestSafetyIdentifier:
    USER_ID = 1234567890123456789
    SECRET_KEY = b"operator-secret"

    def _identifier(self, monkeypatch, user_id: int, key: bytes | None) -> str | None:
        monkeypatch.setattr("discord_claude.util.SAFETY_IDENTIFIER_KEY", key)
        return build_safety_identifier(user_id)

    def test_is_64_lowercase_hex_chars(self, monkeypatch):
        result = self._identifier(monkeypatch, self.USER_ID, self.SECRET_KEY)
        assert result is not None
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result) is True

    def test_is_hmac_sha256_of_the_decimal_user_id(self, monkeypatch):
        expected = hmac.new(self.SECRET_KEY, str(self.USER_ID).encode(), hashlib.sha256).hexdigest()
        assert self._identifier(monkeypatch, self.USER_ID, self.SECRET_KEY) == expected

    def test_deterministic_per_user_and_key(self, monkeypatch):
        first = self._identifier(monkeypatch, self.USER_ID, self.SECRET_KEY)
        second = self._identifier(monkeypatch, self.USER_ID, self.SECRET_KEY)
        assert first == second

    def test_differs_across_users(self, monkeypatch):
        first = self._identifier(monkeypatch, 1, self.SECRET_KEY)
        second = self._identifier(monkeypatch, 2, self.SECRET_KEY)
        assert first != second

    def test_differs_across_keys(self, monkeypatch):
        first = self._identifier(monkeypatch, self.USER_ID, b"secret-a")
        second = self._identifier(monkeypatch, self.USER_ID, b"secret-b")
        assert first != second

    def test_does_not_expose_the_raw_or_unkeyed_id(self, monkeypatch):
        result = self._identifier(monkeypatch, self.USER_ID, self.SECRET_KEY)
        assert result is not None
        unkeyed = hashlib.sha256(str(self.USER_ID).encode()).hexdigest()
        assert result != str(self.USER_ID)
        assert result != format(self.USER_ID, "x")
        assert result != unkeyed
        assert not unkeyed.startswith(result[:16])
        assert str(self.USER_ID) not in result
        assert format(self.USER_ID, "x") not in result

    def test_no_identifier_without_a_key(self, monkeypatch):
        assert self._identifier(monkeypatch, self.USER_ID, None) is None

    def test_request_metadata_carries_the_identifier_as_user_id(self, monkeypatch):
        monkeypatch.setattr("discord_claude.util.SAFETY_IDENTIFIER_KEY", self.SECRET_KEY)
        expected = hmac.new(self.SECRET_KEY, str(self.USER_ID).encode(), hashlib.sha256).hexdigest()
        assert request_metadata(self.USER_ID) == {"user_id": expected}

    def test_request_metadata_is_none_without_a_key(self, monkeypatch):
        monkeypatch.setattr("discord_claude.util.SAFETY_IDENTIFIER_KEY", None)
        assert request_metadata(self.USER_ID) is None


class TestDeriveSafetyIdentifierKey:
    def test_secret_overrides_bot_token(self):
        key = derive_safety_identifier_key("operator-secret", "discord-token")
        assert key == b"operator-secret"

    def test_secret_is_utf8_encoded(self):
        assert derive_safety_identifier_key("s\u00e9cret", None) == "s\u00e9cret".encode()

    def test_falls_back_to_a_key_derived_from_the_bot_token(self):
        expected = hmac.new(b"discord-token", b"safety-identifier-v1", hashlib.sha256).digest()
        assert SAFETY_IDENTIFIER_KEY_LABEL == b"safety-identifier-v1"
        assert derive_safety_identifier_key(None, "discord-token") == expected
        assert derive_safety_identifier_key("", "discord-token") == expected

    def test_bot_token_fallback_is_not_the_raw_token(self):
        assert derive_safety_identifier_key(None, "discord-token") != b"discord-token"

    def test_different_bot_tokens_give_different_keys(self):
        assert derive_safety_identifier_key(None, "token-a") != derive_safety_identifier_key(
            None, "token-b"
        )

    def test_no_key_without_secret_or_bot_token(self):
        assert derive_safety_identifier_key(None, None) is None
        assert derive_safety_identifier_key("", "") is None

    @pytest.mark.parametrize(
        ("secret", "bot_token", "expected"),
        [
            pytest.param(
                None,
                "tok",
                "e4c4e9a56e63186621396e88847c96bf5ebd4caae31c5b1097c7933eb939c85e",
                id="bot-token-fallback",
            ),
            pytest.param(
                "shared-secret",
                "tok",
                "1f4ae57d70d012644d5b186e086ba1651888e8dbb7cc311b6f9fefee5dc8862f",
                id="secret-set",
            ),
        ],
    )
    def test_fixed_vectors_shared_with_sibling_bots(self, monkeypatch, secret, bot_token, expected):
        """The same literal values discord-openai, discord-openrouter and discord-grok
        produce for user 111222333, so a change to how the key or the user ID is
        encoded fails here instead of giving one user different values per bot."""
        key = derive_safety_identifier_key(secret, bot_token)
        monkeypatch.setattr("discord_claude.util.SAFETY_IDENTIFIER_KEY", key)
        assert build_safety_identifier(111222333) == expected
        assert build_safety_identifier("111222333") == expected

    def test_module_key_uses_the_secret_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("SAFETY_IDENTIFIER_SECRET", "env-secret")
        with _fresh_util_module(monkeypatch) as util:
            assert util.SAFETY_IDENTIFIER_KEY == b"env-secret"

    def test_module_key_falls_back_to_bot_token_from_the_environment(self, monkeypatch):
        monkeypatch.delenv("SAFETY_IDENTIFIER_SECRET", raising=False)
        monkeypatch.setenv("BOT_TOKEN", "env-bot-token")
        expected = derive_safety_identifier_key(None, "env-bot-token")
        with _fresh_util_module(monkeypatch) as util:
            assert expected == util.SAFETY_IDENTIFIER_KEY

    def test_module_sends_no_identifier_without_either_env_var(self, monkeypatch):
        monkeypatch.delenv("SAFETY_IDENTIFIER_SECRET", raising=False)
        monkeypatch.delenv("BOT_TOKEN", raising=False)
        with _fresh_util_module(monkeypatch) as util:
            assert util.SAFETY_IDENTIFIER_KEY is None
            assert util.build_safety_identifier(123) is None
            assert util.request_metadata(123) is None


@contextmanager
def _fresh_util_module(monkeypatch):
    """Import discord_claude.config.auth and discord_claude.util again from the env."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_, **__: None)
    # Keep the package attributes pointing at the original modules after the test.
    monkeypatch.setattr(discord_claude.config, "auth", discord_claude.config.auth)
    monkeypatch.setattr(discord_claude, "util", discord_claude.util)
    names = ("discord_claude.config.auth", "discord_claude.util")
    saved = {name: sys.modules[name] for name in names if name in sys.modules}
    for name in names:
        sys.modules.pop(name, None)
    try:
        importlib.import_module("discord_claude.config.auth")
        yield importlib.import_module("discord_claude.util")
    finally:
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(saved)
