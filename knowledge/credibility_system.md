# Thesis Credibility System

## Purpose

Every stock thesis in this system carries a credibility score (0.0 to 1.0).
This score reflects how often the thesis has been validated by real price movements.
Higher credibility theses rank higher in search results and should be weighted more heavily in recommendations.

## How Credibility Works

**Initial score**: 0.5 (neutral prior — no evidence either way)

**Weekly validation** (runs every Monday via weekly_monitor):
- If the stock moved >10% AND the price direction is CONSISTENT with the thesis → credibility += 0.1
- If the stock moved >10% AND the price direction CONTRADICTS the thesis → credibility -= 0.1
- Bounds: [0.0, 1.0]

**Search re-ranking formula**:
adjusted_score = semantic_similarity × (0.6 + 0.4 × credibility)

This means:
- credibility = 1.0 → +40% boost over raw similarity
- credibility = 0.5 → neutral (×0.8 factor, no boost or penalty)
- credibility = 0.0 → -40% penalty

## Thesis Sources

**conversation**: Auto-extracted by Claude Haiku after each substantive chat response. User doesn't need to do anything — the bot identifies stocks it analyzed and saves the thesis.

**weekly_research**: Generated every Monday 08:00 UTC from full market screening. Claude Sonnet analyzes top weekly gainers and identifies 5 undervalued picks with similar growth potential.

**on_demand_discovery**: Triggered when the recommendations database is empty or all theses have low credibility. Scans 60+ candidates and uses Haiku to identify the best picks.

## How to Use Credibility in Reasoning

- Thesis with credibility ≥ 0.7: battle-tested, high weight in recommendations
- Thesis with credibility 0.5-0.7: moderate confidence, use with context
- Thesis with credibility < 0.5: speculative or contradicted, flag as such
- When recommending stocks, always surface the credibility score to calibrate confidence

## Continuous Improvement

The credibility system is the core learning mechanism of this bot.
Over time, theses that consistently predict price movements accumulate higher scores,
and the bot's recommendations naturally improve without any manual intervention.
This is the "snowball" effect: more usage → more theses → more weekly validations → better signal.
