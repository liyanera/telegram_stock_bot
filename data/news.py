import httpx
import config


def get_stock_news(ticker: str, company_name: str = "", max_articles: int = 5) -> list[dict]:
    """Fetch recent news. Uses NewsAPI if key available, else yfinance news."""
    if config.NEWS_API_KEY:
        return _newsapi(ticker, company_name, max_articles)
    return _yfinance_news(ticker, max_articles)


def _newsapi(ticker: str, company_name: str, max_articles: int) -> list[dict]:
    query = company_name or ticker
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
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
                "description": a.get("description", ""),
            }
            for a in articles[:max_articles]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def _yfinance_news(ticker: str, max_articles: int) -> list[dict]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        news = t.news or []
        return [
            {
                "title": n.get("title", ""),
                "source": n.get("publisher", ""),
                "published_at": str(n.get("providerPublishTime", "")),
                "url": n.get("link", ""),
                "description": "",
            }
            for n in news[:max_articles]
        ]
    except Exception as e:
        return [{"error": str(e)}]
