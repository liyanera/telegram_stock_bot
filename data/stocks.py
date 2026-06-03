import yfinance as yf
import pandas as pd
from datetime import datetime
from pathlib import Path
try:
    import ta as ta_lib
    HAS_TA = True
except ImportError:
    HAS_TA = False


def _quarter_label(unix_ts) -> Optional[str]:
    """Convert a Unix timestamp to 'YYYYQn' string."""
    if not unix_ts:
        return None
    dt = datetime.utcfromtimestamp(unix_ts)
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}Q{q}"


def _save_earnings_knowledge(ticker: str, quarter: str, data: dict):
    """Append one earnings entry to knowledge/earnings/TICKER.md."""
    kb_dir = Path(__file__).parent.parent / "knowledge" / "earnings"
    kb_dir.mkdir(parents=True, exist_ok=True)
    path = kb_dir / f"{ticker}.md"
    rev = data.get("revenue")
    fcf = data.get("free_cash_flow")
    lines = [f"\n## {quarter} — {datetime.utcnow().strftime('%Y-%m-%d')}"]
    if rev:
        lines.append(f"- Revenue: ${round(rev/1e9, 2)}B")
    growth = data.get("revenue_growth")
    if growth:
        lines.append(f"- Revenue growth YoY: {round(growth*100, 1)}%")
    if data.get("eps"):
        lines.append(f"- EPS (trailing): {data['eps']}")
    if data.get("gross_margin"):
        lines.append(f"- Gross margin: {round(data['gross_margin']*100, 1)}%")
    if data.get("profit_margin"):
        lines.append(f"- Profit margin: {round(data['profit_margin']*100, 1)}%")
    if fcf:
        lines.append(f"- FCF: ${round(fcf/1e9, 2)}B")
    if data.get("analyst_target_price"):
        lines.append(f"- Analyst target: ${data['analyst_target_price']} | {data.get('recommendation','')}")
    with open(path, "a") as f:
        if not path.exists() or path.stat().st_size == 0:
            f.write(f"# Earnings History — {ticker}\n")
        f.write("\n".join(lines) + "\n")




def get_stock_price(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info
    hist = t.history(period="2d")
    if hist.empty:
        return {"error": f"No data found for {ticker}"}

    price = hist["Close"].iloc[-1]
    prev = hist["Close"].iloc[-2] if len(hist) >= 2 else price
    change_pct = ((price - prev) / prev * 100) if prev else 0

    return {
        "ticker": ticker.upper(),
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "volume": int(hist["Volume"].iloc[-1]),
        "market_cap": info.get("marketCap"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "currency": info.get("currency", "USD"),
    }


def get_financials(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info
    result = {
        "ticker": ticker.upper(),
        "company_name": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "eps": info.get("trailingEps"),
        "revenue": info.get("totalRevenue"),
        "revenue_growth": info.get("revenueGrowth"),
        "gross_margin": info.get("grossMargins"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "return_on_equity": info.get("returnOnEquity"),
        "free_cash_flow": info.get("freeCashflow"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "analyst_target_price": info.get("targetMeanPrice"),
        "recommendation": info.get("recommendationKey"),
    }
    # Auto-save earnings snapshot when a new quarter is detected
    _maybe_save_earnings(ticker.upper(), info, result)
    return result


def _maybe_save_earnings(ticker: str, info: dict, data: dict):
    """Save earnings snapshot if this quarter hasn't been recorded yet."""
    quarter = _quarter_label(info.get("mostRecentQuarter"))
    if not quarter:
        return
    try:
        from memory.mysql_memory import get_last_earnings_quarter, save_earnings_snapshot
        if get_last_earnings_quarter(ticker) == quarter:
            return  # already saved
        save_earnings_snapshot(ticker, quarter, data)
        _save_earnings_knowledge(ticker, quarter, data)
    except Exception:
        pass  # never block the main response


def get_technical_indicators(ticker: str, period: str = "3mo") -> dict:
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist.empty:
        return {"error": f"No data found for {ticker}"}

    close = hist["Close"]
    result: dict = {"ticker": ticker.upper(), "period": period}

    if HAS_TA:
        # RSI
        rsi = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
        result["rsi_14"] = round(float(rsi.iloc[-1]), 2) if not rsi.empty else None

        # MACD
        macd_obj = ta_lib.trend.MACD(close)
        result["macd"] = round(float(macd_obj.macd().iloc[-1]), 4)
        result["macd_signal"] = round(float(macd_obj.macd_signal().iloc[-1]), 4)
        result["macd_hist"] = round(float(macd_obj.macd_diff().iloc[-1]), 4)

        # Bollinger Bands
        bb_obj = ta_lib.volatility.BollingerBands(close, window=20)
        result["bb_upper"] = round(float(bb_obj.bollinger_hband().iloc[-1]), 2)
        result["bb_mid"] = round(float(bb_obj.bollinger_mavg().iloc[-1]), 2)
        result["bb_lower"] = round(float(bb_obj.bollinger_lband().iloc[-1]), 2)

        # SMA
        result["sma_50"] = round(float(ta_lib.trend.SMAIndicator(close, window=50).sma_indicator().iloc[-1]), 2) if len(close) >= 50 else None
        result["sma_200"] = round(float(ta_lib.trend.SMAIndicator(close, window=200).sma_indicator().iloc[-1]), 2) if len(close) >= 200 else None
    else:
        # Fallback: manual SMA
        result["sma_20"] = round(float(close.tail(20).mean()), 2)
        result["sma_50"] = round(float(close.tail(50).mean()), 2) if len(close) >= 50 else None
        result["current_price"] = round(float(close.iloc[-1]), 2)

    return result


def get_price_history(ticker: str, period: str = "1mo") -> dict:
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist.empty:
        return {"error": f"No data found for {ticker}"}
    records = []
    for date, row in hist.tail(30).iterrows():
        records.append({
            "date": str(date.date()),
            "open": round(row["Open"], 2),
            "close": round(row["Close"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "volume": int(row["Volume"]),
        })
    return {"ticker": ticker.upper(), "history": records}


def get_analyst_ratings(ticker: str) -> dict:
    """
    Get analyst consensus, recent rating changes, price targets,
    and institutional ownership.
    """
    t = yf.Ticker(ticker)
    info = t.info

    # Recent analyst upgrades/downgrades
    rating_changes = []
    try:
        upgrades = t.upgrades_downgrades
        if upgrades is not None and not upgrades.empty:
            recent = upgrades.head(10).reset_index()
            for _, row in recent.iterrows():
                rating_changes.append({
                    "date": str(row.get("GradeDate", ""))[:10],
                    "firm": row.get("Firm", ""),
                    "from": row.get("FromGrade", ""),
                    "to": row.get("ToGrade", ""),
                    "action": row.get("Action", ""),
                })
    except Exception:
        pass

    # EPS estimates
    eps_estimates = []
    try:
        earnings = t.earnings_estimate
        if earnings is not None and not earnings.empty:
            for period, row in earnings.iterrows():
                eps_estimates.append({
                    "period": str(period),
                    "avg_estimate": row.get("avg", None),
                    "low": row.get("low", None),
                    "high": row.get("high", None),
                    "num_analysts": row.get("numberOfAnalysts", None),
                })
    except Exception:
        pass

    # Revenue estimates
    rev_estimates = []
    try:
        rev = t.revenue_estimate
        if rev is not None and not rev.empty:
            for period, row in rev.iterrows():
                rev_estimates.append({
                    "period": str(period),
                    "avg_estimate": row.get("avg", None),
                    "low": row.get("low", None),
                    "high": row.get("high", None),
                    "growth": row.get("growth", None),
                })
    except Exception:
        pass

    return {
        "ticker": ticker.upper(),
        "consensus": info.get("recommendationKey", "N/A"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
        "target_mean": info.get("targetMeanPrice"),
        "target_high": info.get("targetHighPrice"),
        "target_low": info.get("targetLowPrice"),
        "current_price": info.get("currentPrice"),
        "upside_pct": round(
            (info.get("targetMeanPrice", 0) - info.get("currentPrice", 0))
            / info.get("currentPrice", 1) * 100, 1
        ) if info.get("currentPrice") and info.get("targetMeanPrice") else None,
        "institutional_ownership_pct": round(
            (info.get("heldPercentInstitutions") or 0) * 100, 1
        ),
        "insider_ownership_pct": round(
            (info.get("heldPercentInsiders") or 0) * 100, 1
        ),
        "short_float_pct": round(
            (info.get("shortPercentOfFloat") or 0) * 100, 1
        ),
        "recent_rating_changes": rating_changes[:8],
        "eps_estimates": eps_estimates[:4],
        "revenue_estimates": rev_estimates[:4],
    }
