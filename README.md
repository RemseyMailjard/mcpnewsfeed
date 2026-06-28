# MCP News Feed

A daily-updated Model Context Protocol (MCP) news aggregator hosted on GitHub Pages. Collects articles about MCP servers, clients, security, and tooling in a clean, searchable interface.

**Live site:** [ai-kennis.nl](https://ai-kennis.nl)

## Features

- 📰 **MCP-focused sources** — Official MCP, MCP community, platform blogs, and security coverage
- 🔍 **Search & filter** — Find articles by keyword, blog category, or date range
- ⭐ **Bookmarks** — Save articles for later (stored locally per browser)
- 🌙 **Dark mode** — Easy on the eyes
- 📱 **Responsive** — Works on desktop, tablet, and mobile
- 🤖 **Auto-updated** — GitHub Actions fetches new articles daily at 7 AM EST (12 PM UTC)
- 📅 **Last 30 days** — Keeps only recent articles for a lean, fast experience

## Source Groups

| Group | Example Sources |
|-------|------------------|
| **Official MCP** | Model Context Protocol Blog |
| **MCP Security** | Model Context Protocol Security |
| **Community Builds** | Dev.to MCP |
| **Platform Coverage** | Azure Dev Community, GitHub Blog, Microsoft DevBlogs, Anthropic News |

## Setup

### 1. Create the GitHub repository

```bash
gh repo create mcpnewsfeed --public --source=. --remote=origin
```

### 2. Push the code

```bash
git init
git add .
git commit -m "Initial commit - MCP News Feed"
git push -u origin master
```

### 3. Enable GitHub Pages

Go to **Settings → Pages → Source** and select **Deploy from a branch** → **main** → **/ (root)**.

### 4. Trigger the first data fetch

Go to **Actions → Fetch MCP Feeds → Run workflow** to populate the initial data.

### 5. Visit your site

Your feed will be live at `https://ai-kennis.nl`

## Local Development

To test the feed fetcher locally:

```bash
uv venv
uv pip install -r scripts/requirements.txt
uv run scripts/fetch_feeds.py
```

Then serve the site:

```bash
uv run python -m http.server 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## How It Works

1. **GitHub Actions** runs daily at 7 AM EST / 12 PM UTC (or manually)
2. **Python script** fetches MCP-relevant RSS feeds and filters to explicit MCP topics
3. Articles from the last 30 days are deduplicated, sorted, and saved to `data/mcp-feeds.json`
4. The commit triggers **GitHub Pages** to redeploy
5. The **static frontend** loads the JSON and renders the feed

## License

MIT
