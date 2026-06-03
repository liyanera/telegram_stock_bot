"""Tool definitions for Claude's function calling."""

TOOLS = [
    {
        "name": "get_stock_price",
        "description": (
            "Get the current price, daily change, volume, 52-week range, and market cap "
            "for a stock ticker. Use this when asked about current price or basic quote."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_financials",
        "description": (
            "Get fundamental financial data: P/E ratio, EPS, revenue, margins, debt/equity, "
            "ROE, free cash flow, dividend yield, beta, and analyst target price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_technical_indicators",
        "description": (
            "Get technical analysis indicators: RSI, MACD, Bollinger Bands, SMA 50/200. "
            "Use for technical analysis, momentum, or trend questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "period": {
                    "type": "string",
                    "description": "Data period: 1mo, 3mo, 6mo, 1y",
                    "enum": ["1mo", "3mo", "6mo", "1y"],
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_stock_news",
        "description": (
            "Get recent news articles for a stock. Use when asked about news, sentiment, "
            "or recent events affecting a company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "company_name": {
                    "type": "string",
                    "description": "Company name for better news search, e.g. 'Apple Inc'",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_analyst_ratings",
        "description": (
            "Get Wall Street analyst consensus, recent rating upgrades/downgrades, "
            "price targets (mean/high/low), upside to consensus target, institutional "
            "and insider ownership, short interest, and forward EPS/revenue estimates. "
            "Use when asked about analyst views, price targets, institutional sentiment, "
            "or when doing a comprehensive stock analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_enriched_news",
        "description": (
            "Fetch last 3 days of news for a stock, analyze sentiment (bullish/bearish/neutral), "
            "identify key themes and catalysts/risks, and return an AI-synthesized summary. "
            "Use instead of get_stock_news for deeper news analysis or when sentiment context matters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "company_name": {"type": "string", "description": "Company name for better search"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_recommendations",
        "description": (
            "Get stock recommendations from the internal thesis database, ranked by credibility score. "
            "ALWAYS use this tool when the user asks for stock recommendations, potential picks, "
            "undervalued stocks, what to buy, or any request for a list of suggested stocks. "
            "Returns bull/bear theses with credibility scores (0.0–1.0) based on how many times "
            "each thesis has been validated by real price movements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thesis_type": {
                    "type": "string",
                    "description": "Filter by thesis type",
                    "enum": ["bull", "bear", "all"],
                },
                "min_credibility": {
                    "type": "number",
                    "description": "Minimum credibility score (0.0–1.0). Use 0.0 to include all theses.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of recommendations to return (default 10)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_earnings_history",
        "description": (
            "Get the historical earnings snapshots for a stock — quarterly revenue, EPS, "
            "margins, FCF, and analyst targets across multiple quarters. Use this when asked "
            "about earnings trends, beat/miss patterns, margin trajectory, or fundamental "
            "progress over time. Returns up to 8 quarters of data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_news_theme_history",
        "description": (
            "Get the accumulated news sentiment and theme history for a stock over recent weeks. "
            "Shows recurring catalysts, persistent risks, and sentiment trend. Use when asked "
            "about news patterns, recurring themes, or how sentiment has evolved over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the internal knowledge base for analysis frameworks, investment methodologies, "
            "sector notes, or stored market insights. Use when you need to apply a specific "
            "analysis framework or recall stored research."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, e.g. 'DCF valuation method' or 'tech sector analysis'",
                }
            },
            "required": ["query"],
        },
    },
]
