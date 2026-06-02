"""
Price fetching utilities for different benchmarks.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def get_prev_close(ticker: str) -> float | None:
    """Previous trading day's closing price."""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) >= 2:
            return round(float(hist["Close"].iloc[-2]), 4)
        return None
    except Exception:
        return None


def get_realtime_price(ticker: str) -> float | None:
    """Current market price (best available)."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="1m")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
        return round(float(t.info.get("currentPrice") or t.info.get("regularMarketPrice")), 4)
    except Exception:
        return None


def get_vwap(ticker: str, period: str = "1d") -> float | None:
    """Volume-weighted average price for the day."""
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1m")
        if hist.empty:
            return None
        typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3
        vwap = (typical * hist["Volume"]).sum() / hist["Volume"].sum()
        return round(float(vwap), 4)
    except Exception:
        return None


def get_open_price(ticker: str) -> float | None:
    """Today's opening price."""
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        if not hist.empty:
            return round(float(hist["Open"].iloc[-1]), 4)
        return None
    except Exception:
        return None


def get_close_price(ticker: str) -> float | None:
    """Today's closing price (or most recent close)."""
    try:
        hist = yf.Ticker(ticker).history(period="2d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
        return None
    except Exception:
        return None


def get_prices_batch(tickers: list, price_type: str = "prev_close") -> dict:
    """
    Batch fetch prices for multiple tickers.
    price_type: prev_close | realtime | vwap | open | close
    Returns: {ticker: price}
    """
    func_map = {
        "prev_close": get_prev_close,
        "realtime": get_realtime_price,
        "vwap": get_vwap,
        "open": get_open_price,
        "close": get_close_price,
    }
    fetch = func_map.get(price_type, get_realtime_price)
    result = {}
    for ticker in tickers:
        try:
            result[ticker] = fetch(ticker)
        except Exception:
            result[ticker] = None
    return result


def calculate_gmv(positions: list, prices: dict) -> float:
    """Gross market value of all positions."""
    return sum(
        p["shares"] * prices.get(p["ticker"], p["avg_cost"])
        for p in positions
        if prices.get(p["ticker"]) is not None
    )
