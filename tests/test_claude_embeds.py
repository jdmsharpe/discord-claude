from discord_claude.cogs.claude.responses import ParsedResponse


class TestAppendResponseEmbeds:
    """Tests for the append_response_embeds helper."""

    def test_long_response_is_preserved_for_delivery_batching(self):
        from discord_claude.cogs.claude.embeds import append_response_embeds

        embeds = []
        long_text = "A" * 25000
        append_response_embeds(embeds, long_text)

        assert "".join(embed.description for embed in embeds) == long_text


class TestAppendThinkingEmbeds:
    """Tests for the append_thinking_embeds helper."""

    def test_no_thinking(self):
        from discord_claude.cogs.claude.embeds import append_thinking_embeds

        embeds = []
        append_thinking_embeds(embeds, "")
        assert len(embeds) == 0

    def test_with_thinking(self):
        from discord_claude.cogs.claude.embeds import append_thinking_embeds

        embeds = []
        append_thinking_embeds(embeds, "Some reasoning here")
        assert len(embeds) == 1
        assert embeds[0].title == "Thinking"
        assert embeds[0].description == "||Some reasoning here||"

    def test_long_thinking_truncated(self):
        from discord_claude.cogs.claude.embeds import append_thinking_embeds

        embeds = []
        long_text = "a" * 4000
        append_thinking_embeds(embeds, long_text)
        assert len(embeds) == 1
        assert len(embeds[0].description) < 3600
        assert "[thinking truncated]" in embeds[0].description


class TestAppendCitationsEmbed:
    """Tests for the append_citations_embed helper."""

    def test_no_citations(self):
        from discord_claude.cogs.claude.embeds import append_citations_embed

        embeds = []
        append_citations_embed(embeds, [])
        assert len(embeds) == 0

    def test_with_web_citations(self):
        from discord_claude.cogs.claude.embeds import append_citations_embed

        embeds = []
        citations = [
            {"kind": "web", "url": "https://example.com/1", "title": "First Source"},
            {"kind": "web", "url": "https://example.com/2", "title": "Second Source"},
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert embeds[0].title == "Sources"
        assert "[First Source](https://example.com/1)" in embeds[0].description
        assert "[Second Source](https://example.com/2)" in embeds[0].description

    def test_web_citations_capped_at_20(self):
        from discord_claude.cogs.claude.embeds import append_citations_embed

        embeds = []
        citations = [
            {"kind": "web", "url": f"https://example.com/{i}", "title": f"Source {i}"}
            for i in range(25)
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert "Source 19" in embeds[0].description
        assert "Source 20" not in embeds[0].description

    def test_long_web_links_are_kept_complete_or_omitted(self):
        from discord_claude.cogs.claude.embeds import append_citations_embed

        first_url = "https://example.com/" + "a" * 3500
        second_url = "https://example.org/" + "b" * 1000
        embeds = []
        append_citations_embed(
            embeds,
            [
                {"kind": "web", "url": first_url, "title": "First"},
                {"kind": "web", "url": second_url, "title": "Second"},
            ],
        )

        assert f"[First]({first_url})" in embeds[0].description
        assert second_url not in embeds[0].description
        assert len(embeds[0].description) <= 4000

    def test_with_document_citations(self):
        from discord_claude.cogs.claude.embeds import append_citations_embed

        embeds = []
        citations = [
            {
                "kind": "document",
                "cited_text": "The grass is green.",
                "document_title": "Nature Doc",
                "location": "",
            },
            {
                "kind": "document",
                "cited_text": "Water is essential.",
                "document_title": "Science PDF",
                "location": "p. 5",
            },
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert "The grass is green." in embeds[0].description
        assert "Nature Doc" in embeds[0].description
        assert "Science PDF, p. 5" in embeds[0].description
        assert "> — *Nature Doc*\n\n> Water is essential." in embeds[0].description

    def test_document_citation_line_breaks_stay_inside_the_quote(self):
        """PDF cited_text carries layout newlines; every rendered line must keep the
        `> ` prefix or Discord ends the blockquote at the first one."""
        from discord_claude.cogs.claude.embeds import append_citations_embed

        embeds = []
        citations = [
            {
                "kind": "document",
                "cited_text": "Or three short pages if\nyou're optimistic.\n",
                "document_title": "sample-local-pdf.pdf",
                "location": "p. 1",
            }
        ]
        append_citations_embed(embeds, citations)
        assert embeds[0].description == (
            "> Or three short pages if you're optimistic.\n> — *sample-local-pdf.pdf, p. 1*"
        )

    def test_mixed_web_and_document_citations(self):
        from discord_claude.cogs.claude.embeds import append_citations_embed

        embeds = []
        citations = [
            {"kind": "web", "url": "https://example.com", "title": "Web Source"},
            {
                "kind": "document",
                "cited_text": "Document text.",
                "document_title": "My Doc",
                "location": "p. 2",
            },
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert "[Web Source](https://example.com)" in embeds[0].description
        assert "Document text." in embeds[0].description


class TestAppendStopReasonEmbed:
    """Tests for the append_stop_reason_embed helper."""

    def test_end_turn_no_embed(self):
        from discord_claude.cogs.claude.embeds import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "end_turn")
        assert len(embeds) == 0

    def test_max_tokens(self):
        from discord_claude.cogs.claude.embeds import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "max_tokens")
        assert len(embeds) == 1
        assert embeds[0].title == "Response Truncated"

    def test_model_context_window_exceeded(self):
        from discord_claude.cogs.claude.embeds import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "model_context_window_exceeded")
        assert len(embeds) == 1
        assert embeds[0].title == "Context Limit Reached"

    def test_refusal(self):
        from discord_claude.cogs.claude.embeds import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "refusal")
        assert len(embeds) == 1
        assert embeds[0].title == "Request Declined"

    def test_refusal_with_stop_details(self):
        from discord_claude.cogs.claude.embeds import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(
            embeds,
            "refusal",
            {
                "type": "refusal",
                "category": "cyber",
                "explanation": "This request would provide harmful cyber guidance.",
            },
        )
        assert len(embeds) == 1
        assert embeds[0].title == "Request Declined"
        assert "Category: `cyber`" in embeds[0].description
        assert "harmful cyber guidance" in embeds[0].description

    def test_pause_turn_no_embed(self):
        from discord_claude.cogs.claude.embeds import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "pause_turn")
        assert len(embeds) == 0


class TestAppendPricingEmbed:
    """Tests for the append_pricing_embed helper."""

    def _make_parsed(self, **kwargs):
        defaults = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "web_search_requests": 0,
            "web_fetch_requests": 0,
            "code_execution_requests": 0,
        }
        defaults.update(kwargs)
        parsed = ParsedResponse()
        for key, value in defaults.items():
            setattr(parsed, key, value)
        return parsed

    def _line(self, parsed, request_cost=0.01, daily_cost=0.10):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        append_pricing_embed(embeds, parsed, request_cost=request_cost, daily_cost=daily_cost)
        assert len(embeds) == 1
        return embeds[0].description

    def test_basic_pricing_embed(self):
        from discord import Colour

        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(input_tokens=1000, output_tokens=500)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.50)
        assert len(embeds) == 1
        assert embeds[0].description == "$0.0100 · 1k in / 500 out · $0.50 today"
        assert embeds[0].color == Colour.orange()

    def test_input_count_includes_cache_reads_and_writes(self):
        """usage.input_tokens excludes cache reads and writes, so the line adds both;
        only cache reads are shown as cached."""
        parsed = self._make_parsed(
            input_tokens=8,
            cache_creation_tokens=40,
            cache_read_tokens=12_457,
            output_tokens=405,
            thinking_tokens=80,
            web_search_requests=2,
        )
        assert self._line(parsed, request_cost=0.0871, daily_cost=0.0871) == (
            "$0.0871 · 12.5k in (12.5k cached) / 405 out (80 thinking) · 2 searches · $0.09 today"
        )

    def test_pricing_embed_with_cache_hits(self):
        parsed = self._make_parsed(cache_read_tokens=5000)
        assert self._line(parsed) == "$0.0100 · 6k in (5k cached) / 500 out · $0.10 today"

    def test_cache_writes_count_as_input_but_not_as_cached(self):
        parsed = self._make_parsed(input_tokens=100, cache_creation_tokens=2_000)
        assert self._line(parsed) == "$0.0100 · 2.1k in / 500 out · $0.10 today"

    def test_pricing_embed_with_web_searches(self):
        parsed = self._make_parsed(web_search_requests=3)
        assert self._line(parsed) == "$0.0100 · 1k in / 500 out · 3 searches · $0.10 today"

    def test_pricing_embed_with_advisor_calls(self):
        """The advisor model's tokens are billed in the request cost but are not
        added to the token counts."""
        parsed = self._make_parsed(
            advisor_calls=2,
            advisor_input_tokens=50_000,
            advisor_output_tokens=2_000,
            advisor_cache_read_tokens=10_000,
        )
        assert (
            self._line(parsed, request_cost=0.15, daily_cost=0.35)
            == "$0.1500 · 1k in / 500 out · 2 advisor calls · $0.35 today"
        )

    def test_pricing_embed_single_search_no_plural(self):
        parsed = self._make_parsed(web_search_requests=1)
        assert self._line(parsed) == "$0.0100 · 1k in / 500 out · 1 search · $0.10 today"

    def test_pricing_embed_with_web_fetches(self):
        parsed = self._make_parsed(web_fetch_requests=2)
        assert self._line(parsed) == "$0.0100 · 1k in / 500 out · 2 fetches · $0.10 today"

    def test_pricing_embed_with_code_execution(self):
        parsed = self._make_parsed(code_execution_requests=1)
        assert self._line(parsed) == "$0.0100 · 1k in / 500 out · 1 code run · $0.10 today"

    def test_tool_counts_follow_the_fleet_order(self):
        parsed = self._make_parsed(
            advisor_calls=1,
            code_execution_requests=3,
            web_fetch_requests=2,
            web_search_requests=1,
        )
        assert self._line(parsed) == (
            "$0.0100 · 1k in / 500 out · 1 search · 2 fetches · 3 code runs · 1 advisor call"
            " · $0.10 today"
        )

    def test_pricing_embed_no_server_tools_hidden(self):
        assert self._line(self._make_parsed()) == "$0.0100 · 1k in / 500 out · $0.10 today"


class TestContextEmbeds:
    """Tests for context warning and compaction embed helpers."""

    def test_context_warning_embed(self):
        from discord_claude.cogs.claude.embeds import append_context_warning_embed

        embeds = []
        append_context_warning_embed(embeds)
        assert len(embeds) == 1
        assert embeds[0].title == "Context Window Warning"
        assert "85%" in embeds[0].description

    def test_compaction_embed(self):
        from discord_claude.cogs.claude.embeds import append_compaction_embed

        embeds = []
        append_compaction_embed(embeds)
        assert len(embeds) == 1
        assert embeds[0].title == "Context Compacted"
        assert "summarized" in embeds[0].description


class TestFallbackEmbed:
    """Tests for the append_fallback_embed helper."""

    def test_no_embed_when_no_fallback(self):
        from discord_claude.cogs.claude.embeds import append_fallback_embed

        embeds = []
        append_fallback_embed(embeds, "claude-fable-5", None)
        assert embeds == []

    def test_no_embed_when_served_by_requested_model(self):
        from discord_claude.cogs.claude.embeds import append_fallback_embed

        embeds = []
        append_fallback_embed(embeds, "claude-fable-5", "claude-fable-5")
        assert embeds == []

    def test_embed_when_fallback_served(self):
        from discord_claude.cogs.claude.embeds import append_fallback_embed

        embeds = []
        append_fallback_embed(embeds, "claude-fable-5", "claude-opus-4-8")
        assert len(embeds) == 1
        assert embeds[0].title == "Model Fallback"
        assert "claude-fable-5" in embeds[0].description
        assert "claude-opus-4-8" in embeds[0].description
