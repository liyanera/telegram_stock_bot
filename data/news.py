from datetime import datetime, timedelta
import httpx
import config


def get_stock_news(ticker: str, company_name: str = "", max_articles: int = 15) -> list[dict]:
    """Fetch last 3 days of news. Uses NewsAPI if key available, else yfinance."""
    if config.NEWS_API_KEY:
        return _newsapi(ticker, company_name, max_articles)
    return _yfinance_news(ticker, max_articles)


def _newsapi(ticker: str, company_name: str, max_articles: int) -> list[dict]:
    query = company_name or ticker
    from_date = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "pageSize": max_articles,
        "language": "en",
        "apiKey": config.NEWS_API_KEY,
    }
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        articles = r.json().get("articles", [])
        return [
            {
                "title": a["title"],
                "source": a["source"]["name"],
                "published_at": a["publishedAt"],
                "url": a["url"],
                "description": a.get("description", "") or "",
            }
            for a in articles[:max_articles]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _yfinance_news(ticker: str, max_articles: int) -> list[dict]:
    try:
        import yfinance as yf
        from datetime import timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        t = yf.Ticker(ticker)
        news = t.news or []
        results = []
        for n in news:
            pub_time = n.get("providerPublishTime", 0)
            if pub_time:
                from datetime import timezone as tz
                pub_dt = datetime.fromtimestamp(pub_time, tz=tz.utc)
                if pub_dt < cutoff:
                    continue
            results.append({
                "title": n.get("title", ""),
                "source": n.get("publisher", ""),
                "published_at": str(pub_time),
                "url": n.get("link", ""),
                "description": "",
            })
            if len(results) >= max_articles:
                break
        return results
    except Exception as e:
        return [{"error": str(e)}]
