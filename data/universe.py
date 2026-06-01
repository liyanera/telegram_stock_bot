"""
Dynamic stock universe — fetches S&P 500 + Nasdaq 100 + high-growth extras.
Uses batch yfinance download for fast weekly performance screening,
then returns top candidates for deep analysis.
"""
import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# Supplemental high-growth / innovation stocks not always in S&P 500
_EXTRA_GROWTH = [
    "PLTR","DDOG","NET","CRWD","ZS","GTLB","MDB","CFLT","TTD","HUBS",
    "BILL","VEEV","HOOD","SOFI","COIN","AFRM","RIVN","NIO","XPEV","LI",
    "SMCI","ARM","MRVL","AVGO","DUOL","RBLX","ROKU","DASH","ABNB","UBER",
    "SNOW","FTNT","PAYC","WDAY","NOW","CRM","ORCL","SHOP","GTLB","ANET",
]


def get_sp500_tickers() -> list[str]:
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )
        tickers = tables[0]["Symbol"].tolist()
        # yfinance uses dashes not dots (e.g. BRK-B not BRK.B)
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        logger.warning(f"Failed to fetch S&P 500 from Wikipedia: {e}")
        return []


def get_nasdaq100_tickers() -> list[str]:
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            attrs={"id": "constituents"},
        )
        tickers = tables[0]["Ticker"].tolist()
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        logger.warning(f"Failed to fetch Nasdaq 100: {e}")
        return []


def get_full_universe() -> list[str]:
    """Return deduplicated universe of S&P 500 + Nasdaq 100 + growth extras."""
    sp500 = get_sp500_tickers()
    ndx = get_nasdaq100_tickers()
    combined = list(dict.fromkeys(sp500 + ndx + _EXTRA_GROWTH))  # deduplicate, preserve order
    logger.info(f"Universe: {len(combined)} tickers (S&P500={len(sp500)}, NDX={len(ndx)}, extras={len(_EXTRA_GROWTH)})")
    return combined


def screen_by_weekly_performance(
    tickers: list[str],
    top_n: int = 60,
    min_market_cap_b: float = 2.0,
) -> pd.DataFrame:
    """
    Batch-download 1-week price data for all tickers (single fast call),
    calculate weekly return, filter by market cap, return top_n performers.
    """
    logger.info(f"Batch downloading weekly prices for {len(tickers)} tickers...")
    try:
        # Single bulk download — much faster than individual calls
        data = yf.download(
            tickers,
            period="5d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )["Close"]
    except Exception as e:
        logger.error(f"Batch download failed: {e}")
        return pd.DataFrame()

    if data.empty:
        return pd.DataFrame()

    # Calculate weekly return
    weekly_returns = ((data.iloc[-1] - data.iloc[0]) / data.iloc[0] * 100).dropna()
    df = weekly_returns.reset_index()
    df.columns = ["ticker", "weekly_return_pct"]
    df["weekly_return_pct"] = df["weekly_return_pct"].round(2)

    # Filter out micro/nano caps via quick info check (sample only the top performers)
    top_candidates = df.sort_values("weekly_return_pct", ascending=False).head(top_n * 2)

    results = []
    checked = 0
    for _, row in top_candidates.iterrows():
        if checked >= top_n:
            break
        try:
            info = yf.Ticker(row["ticker"]).info
            mkt_cap = (info.get("marketCap") or 0) / 1e9
            if mkt_cap >= min_market_cap_b:
                results.append({
                    "ticker": row["ticker"],
                    "weekly_return_pct": row["weekly_return_pct"],
                    "market_cap_b": round(mkt_cap, 1),
                    "company": info.get("shortName", row["ticker"]),
                    "sector": info.get("sector", ""),
                })
                checked += 1
        except Exception:
            continue

    return pd.DataFrame(results).sort_values("weekly_return_pct", ascending=False)
