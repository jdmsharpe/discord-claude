from unittest.mock import MagicMock

import pytest

from discord_claude.util import (
    ADAPTIVE_ONLY_THINKING_MODELS,
    ADAPTIVE_THINKING_MODELS,
    ADVISOR_MODEL_COMPATIBILITY,
    CHUNK_TEXT_SIZE,
    DISCORD_EMBED_TOTAL_LIMIT,
    EFFORT_MODELS,
    EXTENDED_THINKING_MODELS,
    MAX_EFFORT_MODELS,
    MODEL_CONTEXT_WINDOWS,
    REFUSAL_FALLBACK_BETA,
    REFUSAL_FALLBACK_MODEL,
    REFUSAL_FALLBACK_MODELS,
    SAMPLING_LOCKED_MODELS,
    XHIGH_EFFORT_MODELS,
    ChatCompletionParameters,
    Conversation,
    UsageTotals,
    available_embed_space,
    calculate_cost,
    chunk_text,
    format_anthropic_error,
    get_default_advisor_model,
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

    def test_opus_4_7_context_window(self):
        """Opus 4.7 uses the 1M token context window."""
        assert MODEL_CONTEXT_WINDOWS["claude-opus-4-7"] == 1_000_000

    def test_opus_5_context_window(self):
        """Opus 5 ships the 1M token context window with no beta header."""
        assert MODEL_CONTEXT_WINDOWS["claude-opus-5"] == 1_000_000


class TestModelCapabilitySets:
    """Guards for the per-model capability sets consumed by build_api_params."""

    def test_manual_compaction_trigger_bounded_by_summarizer(self):
        """A 1M-window model on the manual path must not out-scale the summarizer.

        compact_conversation hands the whole message list to
        COMPACTION_SUMMARY_MODEL, so an unbounded 75% trigger on a 1M-window
        model would send it ~750k tokens and 400. No selectable manual-path
        model has a 1M window today (claude-opus-5 moved to COMPACTION_MODELS),
        so this pins the guard rather than a live bound.

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

        # The 1M case is the regression: bounded by the summarizer, not the model.
        assert manual_compaction_trigger(1_000_000) == summary_window * 0.75
        assert manual_compaction_trigger(1_000_000) < summary_window

        # A window at or below the summarizer's is unaffected.
        assert manual_compaction_trigger(200_000) == 200_000 * 0.75
        assert manual_compaction_trigger(100_000) == 100_000 * 0.75

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

    def test_advisor_model_compatibility_matches_docs_table(self):
        """Pins the executor -> advisor table from the advisor-tool docs (verified 2026-08-28).

        Tuple order matters: get_default_advisor_model takes the first entry, so
        claude-opus-4-8 leads wherever it is allowed (plaintext advice) and the
        Opus 5 / Fable 5 executors, which only accept Opus 5 / Fable 5 advisors,
        default to claude-opus-5 (encrypted advisor_redacted_result).
        claude-mythos-5 is in the docs table but not publicly callable;
        claude-sonnet-4-5 and claude-opus-4-5 are not executors.
        """
        assert ADVISOR_MODEL_COMPATIBILITY == {
            "claude-haiku-4-5": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-5",
                "claude-fable-5",
                "claude-sonnet-5",
                "claude-sonnet-4-6",
            ),
            "claude-sonnet-4-6": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-5",
                "claude-fable-5",
                "claude-sonnet-5",
                "claude-sonnet-4-6",
            ),
            "claude-sonnet-5": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-fable-5",
                "claude-sonnet-5",
            ),
            "claude-opus-4-6": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-5",
                "claude-fable-5",
                "claude-sonnet-5",
            ),
            "claude-opus-4-7": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-fable-5",
            ),
            "claude-opus-4-8": (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-5",
                "claude-fable-5",
            ),
            "claude-opus-5": ("claude-opus-5", "claude-fable-5"),
            "claude-fable-5": ("claude-opus-5", "claude-fable-5"),
        }
        assert "claude-mythos-5" not in ADVISOR_MODEL_COMPATIBILITY
        for advisors in ADVISOR_MODEL_COMPATIBILITY.values():
            assert "claude-mythos-5" not in advisors

    def test_default_advisor_model_prefers_plaintext_opus_4_8(self):
        """The auto-picked advisor is Opus 4.8 wherever the API allows it.

        Only Opus 5 / Fable 5 executors fall through to claude-opus-5; models
        outside the table (Sonnet 4.5, Opus 4.5) get no advisor at all.
        """
        for executor in (
            "claude-haiku-4-5",
            "claude-sonnet-4-6",
            "claude-sonnet-5",
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-opus-4-8",
        ):
            assert get_default_advisor_model(executor) == "claude-opus-4-8", executor
        for executor in ("claude-opus-5", "claude-fable-5"):
            assert get_default_advisor_model(executor) == "claude-opus-5", executor
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

    def test_retired_opus_4_1_absent_from_capability_sets(self):
        """Opus 4.1 shut down 2026-08-05; its thinking config is dead once unselectable."""
        assert "claude-opus-4-1" not in EXTENDED_THINKING_MODELS

    def test_refusal_fallback_models_are_the_classifier_models(self):
        """Anthropic's refusals page names Fable 5 and Opus 5 as the models with safety
        classifiers (verified 2026-08-28); the Opus 4.8 target carries none, which is what
        makes it a fallback rather than another refusal."""
        assert {"claude-fable-5", "claude-opus-5"} == REFUSAL_FALLBACK_MODELS
        assert REFUSAL_FALLBACK_MODEL == "claude-opus-4-8"
        assert REFUSAL_FALLBACK_MODEL not in REFUSAL_FALLBACK_MODELS
        assert REFUSAL_FALLBACK_BETA == "server-side-fallback-2026-06-01"

    def test_effort_model_sets_membership(self):
        """Pins the per-model effort gate (live-probed 2026-08-28).

        Sonnet 4.5 / Haiku 4.5 reject the parameter, Opus 4.5 stops at high,
        the 4.6 pair adds max but not xhigh, everything newer takes all five.
        """
        assert {
            "claude-fable-5",
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-opus-4-5",
        } == EFFORT_MODELS
        assert {
            "claude-fable-5",
            "claude-opus-5",
            "claude-sonnet-5",
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
            "claude-fable-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-4-8": {"low", "medium", "high", "xhigh", "max"},
            "claude-sonnet-5": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-4-7": {"low", "medium", "high", "xhigh", "max"},
            "claude-opus-4-6": {"low", "medium", "high", "max"},
            "claude-sonnet-4-6": {"low", "medium", "high", "max"},
            "claude-opus-4-5": {"low", "medium", "high"},
            "claude-sonnet-4-5": set(),
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
        """fallback_message iterations (refusal fallback) count as executor usage."""
        totals = UsageTotals()
        usage = MagicMock(
            iterations=[
                # Declined-before-output attempt: reported but unbilled (zeros).
                MagicMock(
                    type="message",
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
                # The attempt served by the fallback model.
                MagicMock(
                    type="fallback_message",
                    input_tokens=150,
                    output_tokens=90,
                    cache_creation_input_tokens=20,
                    cache_read_input_tokens=30,
                ),
            ],
            server_tool_use=None,
        )

        totals.accumulate(usage)

        assert totals.input_tokens == 150
        assert totals.output_tokens == 90
        assert totals.cache_creation_tokens == 20
        assert totals.cache_read_tokens == 30
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
        """context_warning is True when input tokens exceed 85% of window."""
        totals = UsageTotals(input_tokens=175_000)
        target = MagicMock()
        totals.apply_to(target, context_window=200_000)
        assert target.context_warning is True


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
