from discord_claude.cogs.claude.responses import ParsedResponse


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

    def test_basic_pricing_embed(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(input_tokens=1000, output_tokens=500)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.50)
        assert len(embeds) == 1
        desc = embeds[0].description
        assert "1,000 tokens in" in desc
        assert "500 tokens out" in desc
        assert "daily $0.50" in desc

    def test_pricing_embed_with_cache_hits(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(cache_read_tokens=5000)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "5,000 cached" in embeds[0].description

    def test_pricing_embed_with_web_searches(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(web_search_requests=3)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "3 searches" in embeds[0].description

    def test_pricing_embed_single_search_no_plural(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(web_search_requests=1)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "1 search" in embeds[0].description
        assert "searches" not in embeds[0].description

    def test_pricing_embed_with_web_fetches(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(web_fetch_requests=2)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "2 fetches" in embeds[0].description

    def test_pricing_embed_with_code_execution(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(code_execution_requests=1)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "1 code exec" in embeds[0].description
        assert "execs" not in embeds[0].description

    def test_pricing_embed_no_server_tools_hidden(self):
        from discord_claude.cogs.claude.embeds import append_pricing_embed

        embeds = []
        parsed = self._make_parsed()
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        desc = embeds[0].description
        assert "search" not in desc
        assert "fetch" not in desc
        assert "code exec" not in desc


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
