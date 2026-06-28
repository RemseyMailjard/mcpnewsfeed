#!/usr/bin/env python3
"""
MCP News Feed - RSS Feed Fetcher

Fetches articles about Model Context Protocol (MCP), AI agents,
tool integrations, security, developer tooling, and enterprise AI adoption.

Output:
- data/mcp-feeds.json
- data/mcp-feed.xml

Optional:
- AI summary via OPENAI_API_KEY
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring, register_namespace

import feedparser


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

APP_NAME = "MCP News Feed"
OUTPUT_DIR = "data"
JSON_OUTPUT_FILE = "mcp-feeds.json"
RSS_OUTPUT_FILE = "mcp-feed.xml"

DAYS_TO_KEEP = int(os.environ.get("DAYS_TO_KEEP", "30"))
MAX_RSS_ITEMS = int(os.environ.get("MAX_RSS_ITEMS", "50"))
REQUEST_DELAY_SECONDS = float(os.environ.get("REQUEST_DELAY_SECONDS", "0.5"))

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

RSS_SITE_LINK = os.environ.get("RSS_SITE_LINK", "https://mcpfeed.news")

MCP_KEYWORDS = [
    "mcp",
    "model context protocol",
    "modelcontextprotocol",
    "agent",
    "agents",
    "ai agent",
    "ai agents",
    "agentic",
    "tool calling",
    "function calling",
    "tools",
    "mcp server",
    "mcp client",
    "mcp host",
    "copilot",
    "github copilot",
    "claude",
    "openai",
    "anthropic",
    "oauth",
    "authorization",
    "authentication",
    "prompt injection",
    "tool poisoning",
    "enterprise ai",
    "ai-assisted development",
    "developer tooling",
]


@dataclass(frozen=True)
class FeedSource:
    id: str
    name: str
    url: str
    include_all: bool = False
    default_author: str = "Unknown"


# MCP-first sources.
#
# include_all=True means:
# The source is already specifically about MCP, so articles do not need
# additional keyword filtering.
#
# include_all=False means:
# The source is broader, so articles are only included when they match
# MCP-related keywords.
MCP_FEEDS = [
    FeedSource(
        id="mcp-official",
        name="Model Context Protocol Blog",
        url="https://blog.modelcontextprotocol.io/index.xml",
        include_all=True,
        default_author="Model Context Protocol",
    ),
    FeedSource(
        id="mcp-official-rss",
        name="Model Context Protocol Blog RSS",
        url="https://blog.modelcontextprotocol.io/rss.xml",
        include_all=True,
        default_author="Model Context Protocol",
    ),
    FeedSource(
        id="anthropic-news",
        name="Anthropic News",
        url="https://www.anthropic.com/news/rss.xml",
        include_all=False,
        default_author="Anthropic",
    ),
    FeedSource(
        id="github-blog",
        name="GitHub Blog",
        url="https://github.blog/feed/",
        include_all=False,
        default_author="GitHub",
    ),
    FeedSource(
        id="microsoft-developer-blog",
        name="Microsoft Developer Blog",
        url="https://developer.microsoft.com/blog/feed/",
        include_all=False,
        default_author="Microsoft",
    ),
    FeedSource(
        id="microsoft-devblogs",
        name="Microsoft DevBlogs",
        url="https://devblogs.microsoft.com/feed/",
        include_all=False,
        default_author="Microsoft",
    ),
    FeedSource(
        id="azure-dev-community",
        name="Azure Dev Community",
        url="https://techcommunity.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=azuredevcommunityblog",
        include_all=False,
        default_author="Microsoft",
    ),
    FeedSource(
        id="devto-mcp",
        name="Dev.to MCP",
        url="https://dev.to/feed/tag/mcp",
        include_all=True,
        default_author="Dev.to",
    ),
    FeedSource(
        id="devto-ai-agents",
        name="Dev.to AI Agents",
        url="https://dev.to/feed/tag/aiagents",
        include_all=False,
        default_author="Dev.to",
    ),
    FeedSource(
        id="modelcontextprotocol-security",
        name="Model Context Protocol Security",
        url="https://modelcontextprotocol-security.io/rss.xml",
        include_all=True,
        default_author="MCP Security",
    ),
]


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(APP_NAME)


# ------------------------------------------------------------
# Text helpers
# ------------------------------------------------------------

def clean_html(text: str | None) -> str:
    """Remove HTML tags and clean up whitespace."""
    if not text:
        return ""

    text = re.sub(r"<script.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def truncate(text: str, max_length: int = 300) -> str:
    """Truncate text to max_length while trying to end at a word boundary."""
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    truncated = text[:max_length].rsplit(" ", 1)[0]

    if not truncated:
        truncated = text[:max_length]

    return truncated.rstrip() + "..."


def normalize_link(link: str | None) -> str:
    """Normalize article links for deduplication."""
    if not link:
        return ""

    link = link.strip()

    # Remove common tracking fragments where possible.
    link = re.sub(r"#.*$", "", link)

    return link


# ------------------------------------------------------------
# Date helpers
# ------------------------------------------------------------

def parse_date_to_datetime(entry: Any) -> datetime:
    """
    Parse a date from a feed entry.

    Priority:
    1. published_parsed
    2. updated_parsed
    3. published
    4. updated
    5. current UTC time
    """

    for field in ["published_parsed", "updated_parsed"]:
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

    for field in ["published", "updated"]:
        date_str = entry.get(field)
        if not date_str:
            continue

        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError, IndexError, AttributeError):
            pass

        try:
            normalized = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            pass

    return datetime.now(timezone.utc)


def datetime_to_iso(dt: datetime) -> str:
    """Return a UTC ISO timestamp."""
    return dt.astimezone(timezone.utc).isoformat()


def datetime_to_rss_date(dt: datetime) -> str:
    """Return an RFC 2822-style RSS date."""
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


# ------------------------------------------------------------
# Article helpers
# ------------------------------------------------------------

def entry_to_article(entry: Any, source: FeedSource) -> dict[str, Any]:
    """Convert a feedparser entry into a normalized article dictionary."""
    published_dt = parse_date_to_datetime(entry)

    summary = (
        entry.get("summary")
        or entry.get("description")
        or entry.get("subtitle")
        or ""
    )

    article = {
        "title": clean_html(entry.get("title", "Untitled")),
        "link": normalize_link(entry.get("link", "")),
        "published": datetime_to_iso(published_dt),
        "publishedDate": published_dt.date().isoformat(),
        "summary": truncate(clean_html(summary)),
        "blog": source.name,
        "blogId": source.id,
        "author": clean_html(entry.get("author", source.default_author)),
        "sourceUrl": source.url,
    }

    return article


def is_mcp_related(article: dict[str, Any]) -> bool:
    """Check whether an article is related to MCP, agents, tools or enterprise AI."""
    searchable_text = " ".join(
        [
            article.get("title", ""),
            article.get("summary", ""),
            article.get("blog", ""),
            article.get("author", ""),
        ]
    ).lower()

    return any(keyword in searchable_text for keyword in MCP_KEYWORDS)


def get_article_datetime(article: dict[str, Any]) -> datetime:
    """Read the normalized article published timestamp as datetime."""
    value = article.get("published", "")

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------
# Feed fetching
# ------------------------------------------------------------

def fetch_feed(source: FeedSource) -> list[dict[str, Any]]:
    """Fetch and parse a single RSS feed."""
    logger.info("Fetching: %s", source.name)

    articles: list[dict[str, Any]] = []

    try:
        feed = feedparser.parse(source.url)

        if feed.bozo and not feed.entries:
            logger.warning("Could not parse feed: %s", source.name)
            return articles

        for entry in feed.entries:
            article = entry_to_article(entry, source)

            if source.include_all or is_mcp_related(article):
                articles.append(article)

        logger.info("Found %s relevant articles from %s", len(articles), source.name)

    except Exception as exc:
        logger.exception("Error fetching %s: %s", source.name, exc)

    return articles


def fetch_all_feeds(sources: list[FeedSource]) -> list[dict[str, Any]]:
    """Fetch articles from all configured feed sources."""
    all_articles: list[dict[str, Any]] = []

    for source in sources:
        articles = fetch_feed(source)
        all_articles.extend(articles)

        if REQUEST_DELAY_SECONDS > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

    return all_articles


# ------------------------------------------------------------
# Filtering and deduplication
# ------------------------------------------------------------

def filter_recent_articles(
    articles: list[dict[str, Any]],
    days_to_keep: int,
) -> list[dict[str, Any]]:
    """Keep only articles newer than the configured cutoff."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    recent_articles = [
        article
        for article in articles
        if get_article_datetime(article) >= cutoff
    ]

    return recent_articles


def deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate articles by link, falling back to title when needed."""
    seen: set[str] = set()
    unique_articles: list[dict[str, Any]] = []

    for article in articles:
        link = article.get("link", "").strip()
        title = article.get("title", "").strip().lower()

        dedupe_key = link or title

        if not dedupe_key:
            continue

        if dedupe_key not in seen:
            seen.add(dedupe_key)
            unique_articles.append(article)

    return unique_articles


def sort_articles_newest_first(
    articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort articles by published date, newest first."""
    return sorted(
        articles,
        key=get_article_datetime,
        reverse=True,
    )


# ------------------------------------------------------------
# RSS output
# ------------------------------------------------------------

def generate_rss_feed(articles: list[dict[str, Any]]) -> None:
    """Generate an RSS feed XML file from the aggregated articles."""
    dc_namespace = "http://purl.org/dc/elements/1.1/"
    register_namespace("dc", dc_namespace)

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = APP_NAME
    SubElement(channel, "link").text = RSS_SITE_LINK
    SubElement(channel, "description").text = (
        "Aggregated news about Model Context Protocol, AI agents, "
        "tool integrations, MCP security, and developer tooling."
    )
    SubElement(channel, "lastBuildDate").text = datetime_to_rss_date(
        datetime.now(timezone.utc)
    )
    SubElement(channel, "generator").text = APP_NAME
    SubElement(channel, "language").text = "en"

    for article in articles[:MAX_RSS_ITEMS]:
        item = SubElement(channel, "item")

        title = article.get("title", "Untitled")
        link = article.get("link", "")
        summary = article.get("summary", "")
        author = article.get("author", "")
        blog = article.get("blog", "")

        SubElement(item, "title").text = title
        SubElement(item, "link").text = link
        SubElement(item, "guid").text = link or title
        SubElement(item, "description").text = summary
        SubElement(item, f"{{{dc_namespace}}}creator").text = author
        SubElement(item, "category").text = blog

        published_dt = get_article_datetime(article)
        if published_dt.year > 1900:
            SubElement(item, "pubDate").text = datetime_to_rss_date(published_dt)

    xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(
        rss,
        encoding="unicode",
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, RSS_OUTPUT_FILE)

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(xml_string)

    logger.info("RSS feed saved to %s", output_path)


# ------------------------------------------------------------
# AI summary
# ------------------------------------------------------------

def generate_ai_summary(articles: list[dict[str, Any]]) -> str | None:
    """Generate an AI summary of today's MCP-related articles using OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        logger.info("No OPENAI_API_KEY set, skipping AI summary")
        return None

    today = datetime.now(timezone.utc).date().isoformat()

    today_articles = [
        article
        for article in articles
        if article.get("publishedDate") == today
    ]

    if not today_articles:
        logger.info("No articles published today, skipping AI summary")
        return None

    try:
        from openai import OpenAI

        titles = "\n".join(
            [
                f"- {article['title']} ({article['blog']})"
                for article in today_articles[:20]
            ]
        )

        prompt = (
            "You are a concise technical news editor. "
            "Summarize today's articles about Model Context Protocol, MCP servers, "
            "AI agents, tool integrations, developer tooling, security, and enterprise AI adoption. "
            "Write 2-3 practical sentences. "
            "Focus on what matters for software developers, IT trainers, consultants, "
            "and organizations adopting AI-assisted development.\n\n"
            f"Articles:\n{titles}"
        )

        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            max_tokens=220,
        )

        summary = response.choices[0].message.content

        if not summary:
            return None

        summary = summary.strip()

        logger.info("AI summary generated")
        return summary

    except Exception as exc:
        logger.exception("AI summary failed: %s", exc)
        return None


# ------------------------------------------------------------
# JSON output
# ------------------------------------------------------------

def save_json_output(
    articles: list[dict[str, Any]],
    summary: str | None = None,
) -> None:
    """Save aggregated MCP articles to a JSON file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data: dict[str, Any] = {
        "name": APP_NAME,
        "topic": "Model Context Protocol",
        "description": (
            "News about MCP, AI agents, MCP servers, tool integrations, "
            "security, developer tooling, and enterprise AI adoption."
        ),
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "daysToKeep": DAYS_TO_KEEP,
        "totalArticles": len(articles),
        "keywords": MCP_KEYWORDS,
        "sources": [
            {
                "id": source.id,
                "name": source.name,
                "url": source.url,
                "includeAll": source.include_all,
            }
            for source in MCP_FEEDS
        ],
        "articles": articles,
    }

    if summary:
        data["summary"] = summary

    output_path = os.path.join(OUTPUT_DIR, JSON_OUTPUT_FILE)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    logger.info("JSON data saved to %s", output_path)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("%s - Fetching RSS Feeds", APP_NAME)
    logger.info("=" * 60)

    all_articles = fetch_all_feeds(MCP_FEEDS)

    logger.info("Fetched %s articles before filtering", len(all_articles))

    sorted_articles = sort_articles_newest_first(all_articles)
    recent_articles = filter_recent_articles(sorted_articles, DAYS_TO_KEEP)
    unique_articles = deduplicate_articles(recent_articles)
    unique_articles = sort_articles_newest_first(unique_articles)

    discarded_count = len(all_articles) - len(unique_articles)

    if discarded_count > 0:
        logger.info(
            "Filtered out %s duplicate, old, or irrelevant articles",
            discarded_count,
        )

    summary = generate_ai_summary(unique_articles)

    save_json_output(unique_articles, summary)
    generate_rss_feed(unique_articles)

    logger.info("=" * 60)
    logger.info(
        "Done! %s MCP-related articles saved to %s/%s",
        len(unique_articles),
        OUTPUT_DIR,
        JSON_OUTPUT_FILE,
    )
    logger.info("RSS feed saved to %s/%s", OUTPUT_DIR, RSS_OUTPUT_FILE)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()