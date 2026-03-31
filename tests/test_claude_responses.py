from unittest.mock import MagicMock


class TestExtractResponseContent:
    """Tests for the extract_response_content helper."""

    def test_text_only(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "Hello!"
        assert parsed.thinking == ""
        assert parsed.citations == []

    def test_thinking_and_text(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "Let me reason about this..."
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "The answer is 42."
        text_block.citations = None
        response.content = [thinking_block, text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "The answer is 42."
        assert parsed.thinking == "Let me reason about this..."

    def test_redacted_thinking_ignored(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        redacted_block = MagicMock()
        redacted_block.type = "redacted_thinking"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        response.content = [redacted_block, text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "Response."
        assert parsed.thinking == ""

    def test_empty_content(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        response.content = []

        parsed = extract_response_content(response)
        assert parsed.text == "No response."
        assert parsed.thinking == ""

    def test_with_web_citations(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "According to sources..."
        citation1 = MagicMock()
        citation1.url = "https://example.com/1"
        citation1.title = "Source 1"
        citation1.cited_text = "cited text 1"
        citation2 = MagicMock()
        citation2.url = "https://example.com/2"
        citation2.title = "Source 2"
        citation2.cited_text = "cited text 2"
        text_block.citations = [citation1, citation2]
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert len(parsed.citations) == 2
        assert parsed.citations[0]["kind"] == "web"
        assert parsed.citations[0]["url"] == "https://example.com/1"
        assert parsed.citations[1]["title"] == "Source 2"

    def test_with_document_citations(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "The document says..."

        char_citation = MagicMock()
        char_citation.url = None
        char_citation.type = "char_location"
        char_citation.cited_text = "The grass is green."
        char_citation.document_title = "My Document"
        char_citation.document_index = 0
        char_citation.start_char_index = 0
        char_citation.end_char_index = 19

        page_citation = MagicMock()
        page_citation.url = None
        page_citation.type = "page_location"
        page_citation.cited_text = "Water is essential."
        page_citation.document_title = "PDF Report"
        page_citation.document_index = 1
        page_citation.start_page_number = 5
        page_citation.end_page_number = 6

        text_block.citations = [char_citation, page_citation]
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert len(parsed.citations) == 2
        assert parsed.citations[0]["kind"] == "document"
        assert parsed.citations[0]["cited_text"] == "The grass is green."
        assert parsed.citations[0]["document_title"] == "My Document"
        assert parsed.citations[0]["location"] == ""
        assert parsed.citations[1]["kind"] == "document"
        assert parsed.citations[1]["cited_text"] == "Water is essential."
        assert parsed.citations[1]["location"] == "p. 5"

    def test_document_citations_multi_page(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Spanning pages..."
        citation = MagicMock()
        citation.url = None
        citation.type = "page_location"
        citation.cited_text = "A long passage."
        citation.document_title = "Report"
        citation.start_page_number = 3
        citation.end_page_number = 6
        text_block.citations = [citation]
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert parsed.citations[0]["location"] == "pp. 3–5"

    def test_document_citations_deduplicated(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        block1 = MagicMock()
        block1.type = "text"
        block1.text = "Part 1"
        cite1 = MagicMock()
        cite1.url = None
        cite1.type = "char_location"
        cite1.cited_text = "Same passage."
        cite1.document_title = "Doc"
        block1.citations = [cite1]

        block2 = MagicMock()
        block2.type = "text"
        block2.text = "Part 2"
        cite2 = MagicMock()
        cite2.url = None
        cite2.type = "char_location"
        cite2.cited_text = "Same passage."
        cite2.document_title = "Doc"
        block2.citations = [cite2]

        response.content = [block1, block2]
        parsed = extract_response_content(response)
        assert len(parsed.citations) == 1

    def test_web_citations_deduplicated(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        text_block1 = MagicMock()
        text_block1.type = "text"
        text_block1.text = "Part 1"
        citation1 = MagicMock()
        citation1.url = "https://example.com/same"
        citation1.title = "Same Source"
        citation1.cited_text = "text"
        text_block1.citations = [citation1]

        text_block2 = MagicMock()
        text_block2.type = "text"
        text_block2.text = "Part 2"
        citation2 = MagicMock()
        citation2.url = "https://example.com/same"
        citation2.title = "Same Source Again"
        citation2.cited_text = "text"
        text_block2.citations = [citation2]

        response.content = [text_block1, text_block2]

        parsed = extract_response_content(response)
        assert len(parsed.citations) == 1

    def test_tool_use_detected(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Let me check."
        text_block.citations = None
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "memory"
        tool_block.input = {"command": "view"}
        response.content = [text_block, tool_block]

        parsed = extract_response_content(response)
        assert len(parsed.tool_use_blocks) == 1
        assert parsed.tool_use_blocks[0].name == "memory"

    def test_server_tool_blocks_skipped(self):
        from discord_claude.cogs.claude.responses import extract_response_content

        response = MagicMock()
        server_block = MagicMock()
        server_block.type = "server_tool_use"
        result_block = MagicMock()
        result_block.type = "web_search_tool_result"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Here are the results."
        text_block.citations = None
        response.content = [server_block, result_block, text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "Here are the results."
        assert len(parsed.tool_use_blocks) == 0
