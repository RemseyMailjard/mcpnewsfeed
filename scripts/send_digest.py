#!/usr/bin/env python3
"""
MCP News Feed - Weekly Digest Sender

Reads the latest mcp-feeds.json, picks the top-10 articles from the past 7 days,
and sends an HTML email to every subscriber via Resend.

Required environment variables:
  RESEND_API_KEY     — Resend API key
  SUBSCRIBERS        — Comma-separated list of subscriber email addresses
  DIGEST_FROM_EMAIL  — Sender address (e.g. "MCP Feed <digest@mcp.news>")

Optional environment variables:
  DIGEST_REPLY_TO    — Reply-to address
  DATA_FILE          — Path to mcp-feeds.json (default: data/mcp-feeds.json)
"""

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("MCP Digest")

DATA_FILE = os.environ.get("DATA_FILE", "data/mcp-feeds.json")
RESEND_API_URL = "https://api.resend.com/emails"
TOP_N = 10
LOOKBACK_DAYS = 7


def load_articles() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("articles", [])


def filter_last_week(articles: list[dict]) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    result = []
    for article in articles:
        try:
            published = datetime.fromisoformat(
                article["published"].replace("Z", "+00:00")
            )
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published >= cutoff:
                result.append(article)
        except (KeyError, ValueError):
            continue
    return result


def build_html(articles: list[dict], week_label: str) -> str:
    rows = ""
    for article in articles:
        try:
            date = datetime.fromisoformat(
                article["published"].replace("Z", "+00:00")
            ).strftime("%b %d")
        except (KeyError, ValueError):
            date = ""

        rows += f"""
        <tr>
          <td style="padding:16px 0;border-bottom:1px solid #e4e6eb;">
            <p style="margin:0 0 4px;font-size:12px;color:#65676b;">{date} &nbsp;·&nbsp; {article.get('blog','')}</p>
            <a href="{article.get('link','')}" style="font-size:16px;font-weight:600;color:#0078D4;text-decoration:none;line-height:1.4;">
              {article.get('title','')}
            </a>
            <p style="margin:6px 0 0;font-size:13px;color:#65676b;line-height:1.5;">
              {article.get('summary','')[:200]}{"…" if len(article.get('summary','')) > 200 else ""}
            </p>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0078D4,#004E8C);border-radius:12px 12px 0 0;padding:24px 32px;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">MCP Feed</h1>
            <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">
              Weekly digest — {week_label}
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="background:#fff;padding:8px 32px 24px;border-radius:0 0 12px 12px;border:1px solid #dadde1;border-top:none;">
            <p style="font-size:14px;color:#65676b;margin:20px 0 8px;">
              Top {len(articles)} MCP articles from the past week, curated for you.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0">
              {rows}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 0;text-align:center;">
            <p style="font-size:12px;color:#8a8d91;margin:0;">
              You're receiving this because you subscribed at mcp.news.<br>
              <a href="https://mcp.news" style="color:#0078D4;">Visit the feed</a>
              &nbsp;·&nbsp;
              <a href="https://mcp.news/suggest.html" style="color:#0078D4;">Suggest a source</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(to: str, subject: str, html: str, api_key: str, from_email: str, reply_to: str | None) -> None:
    payload: dict = {
        "from": from_email,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Sent to %s — status %s", to, resp.status)
    except urllib.error.HTTPError as exc:
        logger.error("Failed to send to %s — HTTP %s: %s", to, exc.code, exc.read().decode())
    except urllib.error.URLError as exc:
        logger.error("Failed to send to %s — %s", to, exc.reason)


def main() -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        logger.error("RESEND_API_KEY not set — aborting")
        return

    subscribers_raw = os.environ.get("SUBSCRIBERS", "")
    subscribers = [s.strip() for s in subscribers_raw.split(",") if s.strip()]
    if not subscribers:
        logger.info("No subscribers configured — nothing to send")
        return

    from_email = os.environ.get("DIGEST_FROM_EMAIL", "MCP Feed <digest@mcp.news>")
    reply_to = os.environ.get("DIGEST_REPLY_TO") or None

    logger.info("Loading articles from %s", DATA_FILE)
    articles = load_articles()
    recent = filter_last_week(articles)[:TOP_N]

    if not recent:
        logger.info("No articles from the past week — skipping digest")
        return

    week_label = datetime.now(timezone.utc).strftime("Week of %B %d, %Y")
    subject = f"MCP Weekly Digest — {week_label}"
    html = build_html(recent, week_label)

    logger.info("Sending digest to %d subscriber(s)", len(subscribers))
    for email in subscribers:
        send_email(email, subject, html, api_key, from_email, reply_to)

    logger.info("Done")


if __name__ == "__main__":
    main()
