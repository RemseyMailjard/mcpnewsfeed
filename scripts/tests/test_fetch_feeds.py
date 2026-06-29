import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fetch_feeds import (
    _first_sentence,
    _build_fallback_summary,
    generate_ai_summary,
    is_mcp_related,
)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _article(title: str, summary: str = "", published_today: bool = True) -> dict:
    return {
        "title": title,
        "summary": summary,
        "publishedDate": _today() if published_today else "2000-01-01",
        "blog": "Test Blog",
        "author": "Tester",
        "link": f"https://example.com/{title.replace(' ', '-')}",
    }


# ---------------------------------------------------------------
# Module 4 — Extended keywords (is_mcp_related)
# ---------------------------------------------------------------

class TestIsMcpRelated:
    def test_tool_calling(self):
        assert is_mcp_related(_article("Introduction to tool calling in AI"))

    def test_mcp_tool(self):
        assert is_mcp_related(_article("New mcp tool released"))

    def test_mcp_integration(self):
        assert is_mcp_related(_article("MCP integration with VS Code"))

    def test_mcp_plugin(self):
        assert is_mcp_related(_article("Build your own MCP plugin"))

    def test_mcp_endpoint(self):
        assert is_mcp_related(_article("Securing the MCP endpoint"))

    def test_mcp_protocol(self):
        assert is_mcp_related(_article("How the MCP protocol works"))

    def test_existing_mcp_server(self):
        assert is_mcp_related(_article("Running an MCP server locally"))

    def test_existing_model_context_protocol(self):
        assert is_mcp_related(_article("Model Context Protocol announcement"))

    def test_unrelated_article(self):
        assert not is_mcp_related(_article("10 tips for better sleep"))

    def test_unrelated_mcp_abbreviation(self):
        # "MCP" alone without a qualifying noun should not match
        assert not is_mcp_related(_article("MCP certification exam tips"))


# ---------------------------------------------------------------
# Module 1 — AI Summary Fallback
# ---------------------------------------------------------------

class TestFirstSentence:
    def test_extracts_first_sentence(self):
        result = _first_sentence("Hello world. This is extra.")
        assert result == "Hello world."

    def test_truncates_at_max_length(self):
        long_text = "a" * 200
        result = _first_sentence(long_text, max_length=150)
        assert result == "a" * 150 + "..."

    def test_empty_string(self):
        assert _first_sentence("") == ""

    def test_no_sentence_end(self):
        text = "Short text"
        assert _first_sentence(text) == "Short text"


class TestBuildFallbackSummary:
    def test_returns_none_when_no_today_articles(self):
        articles = [_article("Old article", published_today=False)]
        result = _build_fallback_summary(articles, _today())
        assert result is None

    def test_contains_article_titles(self):
        articles = [_article(f"Article {i}", summary="First sentence. More text.") for i in range(5)]
        result = _build_fallback_summary(articles, _today())
        assert result is not None
        for i in range(5):
            assert f"Article {i}" in result

    def test_limited_to_five_articles(self):
        articles = [_article(f"Article {i}") for i in range(10)]
        result = _build_fallback_summary(articles, _today())
        assert result is not None
        assert result.count("•") == 5


class TestGenerateAiSummary:
    def test_fallback_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        articles = [_article("MCP news today", summary="Big announcement. More details.")]
        result = generate_ai_summary(articles)
        assert result is not None
        text, source = result
        assert source == "fallback"
        assert "MCP news today" in text

    def test_returns_none_when_no_today_articles(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        articles = [_article("Old article", published_today=False)]
        result = generate_ai_summary(articles)
        assert result is None

    def test_summary_source_is_fallback_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        articles = [_article("Today's MCP update", summary="Something happened.")]
        result = generate_ai_summary(articles)
        assert result is not None
        _, source = result
        assert source == "fallback"
