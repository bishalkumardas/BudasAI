"""Repository boundary. Templates consume normalized rows from Supabase."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html import escape
from html.parser import HTMLParser

from app.config import SUPABASE_ANON_KEY, SUPABASE_URL

_CATEGORY_DESCRIPTIONS = {
    "Equity": "Business quality, valuation and long-term ownership.",
    "Fixed Income": "Rates, credit, duration and portfolio construction.",
    "Markets": "Market structure, indicators and investor context.",
    "CFA Concepts": "Clear explanations of essential investment concepts.",
}
_ARTICLE_IMAGES = {
    "Equity": "/static/images/research-equity.svg",
    "Fixed Income": "/static/images/research-fixed-income.svg",
    "Markets": "/static/images/research-markets.svg",
    "CFA Concepts": "/static/images/research-cfa.svg",
}

_ALLOWED_TAGS = {"a", "b", "blockquote", "br", "code", "em", "h2", "h3", "h4", "hr", "i", "img", "li", "ol", "p", "pre", "strong", "table", "tbody", "td", "th", "thead", "tr", "u", "ul"}
_ALLOWED_ATTRIBUTES = {"a": {"href", "title"}, "img": {"src", "alt", "title", "width", "height"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}}


class _ArticleHTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            return
        safe_attrs = []
        for name, value in attrs:
            if name not in _ALLOWED_ATTRIBUTES.get(tag, set()) or value is None:
                continue
            if name in {"href", "src"} and not value.startswith(("https://", "http://", "/")):
                continue
            safe_attrs.append(f' {name}="{escape(value, quote=True)}"')
        self.output.append(f"<{tag}{''.join(safe_attrs)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _ALLOWED_TAGS and tag not in {"br", "hr", "img"}:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        self.output.append(escape(data))


def _sanitize_article_html(value):
    parser = _ArticleHTMLSanitizer()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.output)


@lru_cache(maxsize=1)
def _client():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _normalize_market(row):
    row["slug"] = row.get("slug") or row["symbol"].lower()
    row["timestamp"] = row.get("timestamp") or row.get("updated_at") or "Latest stored close"
    # Prices are sourced from market_history. Do not manufacture zero-valued
    # observations when a market has not received an import yet.
    row["current_value"] = None
    row["change_percent"] = None
    row["history"] = row.get("history") or []
    return row


def _normalize_article(row):
    row["image"] = row.get("cover_image") or _ARTICLE_IMAGES.get(row.get("category"), "/static/images/research-markets.svg")
    row["blocks"] = row.get("blocks") or []
    row["author"] = row.get("author") or "BudasAI Research"
    row["body_html"] = _sanitize_article_html(row.get("body_html") or "")
    return row


def _all_articles(category=None):
    client = _client()
    if not client:
        rows = []
    else:
        query = client.table("research_articles").select("*").order("published_at", desc=True)
        if category:
            query = query.eq("category", category)
        rows = query.execute().data
    return [_normalize_article(dict(row)) for row in rows]


def get_markets(region=None):
    client = _client()
    if not client:
        return []
    query = client.table("markets").select("*").eq("is_active", True).order("name")
    if region:
        query = query.eq("region", region)
    markets = [_normalize_market(dict(row)) for row in query.execute().data]
    return _attach_recent_histories(markets)


def _attach_recent_histories(markets):
    """Attach history and derive the displayed price from market_history."""
    client = _client()
    if not client or not markets:
        return markets
    market_ids = [market["id"] for market in markets]
    # Do not limit this query to 31 days: an infrequently updated market must
    # still show its latest stored value.
    rows = client.table("market_history").select("market_id,value,timestamp").in_("market_id", market_ids).order("timestamp", desc=True).execute().data
    rows_by_market = {}
    for row in rows:
        rows_by_market.setdefault(row["market_id"], []).append(row)
    for market in markets:
        history_rows = rows_by_market.get(market["id"], [])
        if not history_rows:
            continue
        latest = history_rows[0]
        latest_value = float(latest["value"])
        market["current_value"] = latest_value
        market["timestamp"] = latest["timestamp"]
        market["history"] = [float(row["value"]) for row in reversed(history_rows[:15])]
        if len(history_rows) >= 2:
            previous_value = float(history_rows[1]["value"])
            market["change_percent"] = (
                ((latest_value - previous_value) / previous_value) * 100
                if previous_value != 0 else None
            )
    return markets


def get_market(slug):
    return next((market for market in get_markets() if slug.lower() in {market["slug"].lower(), market["symbol"].lower()}), None)


_HISTORY_PERIODS = {"1W": 7, "1M": 31, "6M": 183, "1Y": 365, "5Y": 365 * 5}


def get_market_history(slug, period="1M"):
    """Return dated observations, ending at the most recent stored point."""
    market = get_market(slug)
    if not market:
        return []
    client = _client()
    if not client:
        return []
    days = _HISTORY_PERIODS.get(period.upper(), _HISTORY_PERIODS["1M"])
    latest = client.table("market_history").select("timestamp").eq("market_id", market["id"]).order("timestamp", desc=True).limit(1).execute().data
    if not latest:
        return []
    latest_at = datetime.fromisoformat(latest[0]["timestamp"].replace("Z", "+00:00"))
    cutoff = (latest_at - timedelta(days=days)).isoformat()
    rows = client.table("market_history").select("timestamp,value").eq("market_id", market["id"]).gte("timestamp", cutoff).order("timestamp").execute().data
    return [{"timestamp": row["timestamp"], "value": float(row["value"])} for row in rows]


def get_articles(category=None, page=1, per_page=6):
    articles = _all_articles(category)
    start = (page - 1) * per_page
    return articles[start:start + per_page], len(articles)


def get_article(slug):
    client = _client()
    if not client:
        return None
    rows = client.table("research_articles").select("*").eq("slug", slug).limit(1).execute().data
    if not rows:
        return None
    article = _normalize_article(dict(rows[0]))
    sources = client.table("research_sources").select("title,url").eq("article_id", article["id"]).execute().data
    if sources and not any(block.get("type") == "source_list" for block in article["blocks"]):
        article["blocks"].append({"type": "source_list", "sources": sources})
    return article


def get_articles_by_category(category):
    return _all_articles(category)


def search_articles(query):
    needle = query.lower().strip()
    if not needle:
        return []
    return [article for article in _all_articles() if needle in (article["title"] + article["excerpt"] + article["category"]).lower()]


def get_categories():
    counts = Counter(article["category"] for article in _all_articles() if article.get("category"))
    return [{"name": name, "description": _CATEGORY_DESCRIPTIONS.get(name, "Research and learning notes."), "article_count": count} for name, count in sorted(counts.items())]
