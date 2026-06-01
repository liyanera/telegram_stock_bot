"""
Weekly Growth Research:
1. Find top 10 large/mid-cap gainers from the past week
2. Research why they surged (fundamentals + news)
3. Identify 5 undervalued stocks with similar growth potential
4. Save findings to ChromaDB knowledge base
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf
import pandas as pd
import anthropic
import config
from data.news import get_stock_news
from data.universe import get_full_universe, screen_by_weekly_performance
from memory.vector_memory import add_knowledge


def get_weekly_performance(tickers: list) -> pd.DataFrame:
    """Use batch screening for speed across full universe."""
    return screen_by_weekly_performance(tickers, top_n=60, min_market_cap_b=2.0)


def get_stock_snapshot(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="1mo")
        news = get_stock_news(ticker, info.get("shortName", ""), max_articles=5)
        return {
            "ticker": ticker,
            "company": info.get("longName", ticker),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "price": round(hist["Close"].iloc[-1], 2) if not hist.empty else None,
            "market_cap_b": round((info.get("marketCap") or 0) / 1e9, 1),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "revenue_growth": info.get("revenueGrowth"),
            "gross_margins": info.get("grossMargins"),
            "profit_margins": info.get("profitMargins"),
            "free_cashflow_b": round((info.get("freeCashflow") or 0) / 1e9, 2),
            "debt_to_equity": info.get("debtToEquity"),
            "beta": info.get("beta"),
            "analyst_target": info.get("targetMeanPrice"),
            "recommendation": info.get("recommendationKey"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "news_headlines": [n.get("title", "") for n in news if "title" in n][:5],
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def analyze_with_claude(top_gainers_data: list, universe_data: list) -> str:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = f"""You are an elite US growth stock analyst. Today is {datetime.now().strftime('%Y-%m-%d')}.

## TASK
Analyze the following data and produce a structured research report.

## TOP 10 WEEKLY GAINERS DATA
{json.dumps(top_gainers_data, indent=2, default=str)}

## ADDITIONAL UNIVERSE DATA (for finding undervalued picks)
{json.dumps(universe_data[:30], indent=2, default=str)}

## INSTRUCTIONS

### Part 1: Why Did These 10 Stocks Surge?
For each of the top 10 gainers, analyze:
- Most likely catalyst (earnings beat, product launch, sector rotation, macro tailwind, analyst upgrade, M&A rumors)
- Whether the move is justified by fundamentals or looks like a sentiment spike
- Sustainability of the move (1-3 sentence verdict)

### Part 2: Find 5 Undervalued Stocks with Similar Growth Potential
Based on the THEMES you identified in Part 1 (e.g. AI infrastructure, GLP-1 drugs, cybersecurity, etc.):
- Find 5 stocks from the universe that share the same tailwinds but haven't moved yet
- They should look undervalued relative to their growth potential
- Rank them #1 (highest conviction) to #5
- For each: thesis (2-3 sentences), key metrics, target price rationale, main risk

### Part 3: Key Themes Summary
Summarize the 2-3 dominant market themes driving gains this week that investors should watch.

Be direct, data-driven, and specific. No generic statements."""

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _git_commit(date_str: str):
    import subprocess
    repo_root = Path(__file__).parent.parent
    try:
        subprocess.run(["git", "add", "knowledge/"], cwd=repo_root, check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_root
        )
        if result.returncode != 0:  # there are staged changes
            subprocess.run(
                ["git", "commit", "-m", f"Weekly research: {date_str}"],
                cwd=repo_root, check=True
            )
            print(f"Git committed: knowledge/weekly_research_{date_str}.md")
        else:
            print("No new knowledge changes to commit.")
    except Exception as e:
        print(f"Git commit skipped: {e}")


def save_to_knowledge_base(report: str, date_str: str):
    doc_id = f"weekly-research-{date_str}"
    add_knowledge(
        doc_id,
        f"Weekly Growth Research Report ({date_str}):\n\n{report}",
        metadata={"type": "weekly_research", "date": date_str},
    )
    print(f"\nSaved to knowledge base: [{doc_id}]")

    # Also save to knowledge/ folder so it persists across Railway redeploys
    out_path = Path(__file__).parent.parent / "knowledge" / f"weekly_research_{date_str}.md"
    out_path.write_text(f"# Weekly Growth Research — {date_str}\n\n{report}")
    print(f"Saved to file: {out_path}")


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"Weekly Growth Research — {date_str}")
    print(f"{'='*60}\n")

    # Step 1: Get top 10 weekly gainers from full market universe
    universe = get_full_universe()
    print(f"Universe size: {len(universe)} tickers")
    perf_df = get_weekly_performance(universe)
    top10 = perf_df.head(10)
    print("\nTop 10 Weekly Gainers:")
    print(top10[["ticker", "company", "weekly_return_pct", "market_cap_b"]].to_string(index=False))

    # Step 2: Get detailed snapshot for top 10
    print("\nFetching detailed data for top 10...")
    top10_data = []
    for _, row in top10.iterrows():
        snap = get_stock_snapshot(row["ticker"])
        snap["weekly_return_pct"] = row["weekly_return_pct"]
        top10_data.append(snap)
        print(f"  {row['ticker']}: +{row['weekly_return_pct']}%")

    # Step 3: Get snapshot for broader universe (for undervalued picks)
    print("\nFetching universe data for undervalued picks...")
    universe_data = []
    remaining = perf_df.iloc[10:50]  # Next 40 stocks
    for _, row in remaining.iterrows():
        snap = get_stock_snapshot(row["ticker"])
        snap["weekly_return_pct"] = row["weekly_return_pct"]
        universe_data.append(snap)

    # Step 4: Claude analysis
    print("\nRunning Claude analysis...")
    report = analyze_with_claude(top10_data, universe_data)

    # Step 5: Print report
    print(f"\n{'='*60}")
    print("RESEARCH REPORT")
    print(f"{'='*60}\n")
    print(report)

    # Step 6: Save to knowledge base + auto-commit to git
    save_to_knowledge_base(report, date_str)
    _git_commit(date_str)
    print("\nDone! The bot can now reference this research in conversations.")


if __name__ == "__main__":
    main()
