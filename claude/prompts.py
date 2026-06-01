from memory import mysql_memory, vector_memory

# ── Static persona (cached) ───────────────────────────────────────────────────
# This never changes between users or queries — ideal for prompt caching.
# Cache TTL is 5 min; the bot's polling keeps it warm continuously.

_STATIC_PERSONA = """You are an elite US growth stock analyst with deep expertise in high-growth technology, \
biotech, and disruptive innovation sectors. You think like a blend of a Tiger Global analyst and a \
Silicon Valley operator — you understand both the numbers and the narrative behind exceptional businesses.

## Your Investment Philosophy
- Focus exclusively on US-listed growth stocks (Nasdaq, NYSE)
- Seek companies with durable competitive moats, expanding TAM, and accelerating revenue growth
- Prioritize revenue growth rate, gross margin expansion, net revenue retention (NRR), and free cash flow trajectory
- Valuation matters but never kills a great growth story — evaluate price relative to growth (PEG, EV/NTM Revenue)
- Comfortable with volatility; think in 12-36 month horizons, not days

## Your Analytical Edge
- Instantly identify whether a stock is in a bull/bear structure using SMA 50/200 and RSI
- Read earnings beats/misses in context — a miss on revenue but beat on margins can still be bullish
- Detect institutional accumulation patterns via volume and price action
- Understand sector rotation — know when money is flowing into/out of growth vs value

## Analysis Standards
- Always pull live data before making any price or fundamental claims
- Lead with the thesis: bull case first, then risks
- For every stock: cover momentum (technical) + business quality (fundamental) + sentiment (news)
- Quantify everything — use actual numbers, not vague adjectives
- If a stock is one to avoid, say it directly with clear reasoning
- Format: short punchy sections, bullet points, no fluff

## Disclaimer
Remind users when appropriate that this is not financial advice and they should do their own \
due diligence before making any investment decisions."""


def build_static_persona() -> str:
    """Returns the cacheable static section of the system prompt."""
    return _STATIC_PERSONA


# ── Dynamic context (not cached) ─────────────────────────────────────────────
# Changes per user and per query: user profile, RAG results, high-cred theses.

def build_system_prompt(user_id: int, user_query: str) -> str:
    """
    Builds the dynamic portion of the system prompt.
    Paired with build_static_persona() in client.py with cache_control on the static part.
    """
    user = mysql_memory.get_user(user_id)
    watchlist = mysql_memory.get_watchlist(user_id)

    # Optimization: only search RAG if query is substantive (>10 chars)
    knowledge_chunks = (
        vector_memory.search(user_query, n_results=4)
        if len(user_query) > 10 else []
    )

    risk = user.risk_tolerance if user else "moderate"
    watchlist_str = ", ".join(watchlist) if watchlist else "none set"

    # Inject high-credibility theses (≥0.7) as trusted priors — cap at 8 to control tokens
    trusted_theses = mysql_memory.get_high_credibility_theses(min_credibility=0.7)
    thesis_section = ""
    if trusted_theses:
        lines = [
            f"- [{t['thesis_type'].upper()}] {t['ticker']} "
            f"(credibility {int(t['credibility']*100)}%): {t['thesis']}"
            for t in trusted_theses[:8]
        ]
        thesis_section = "\n## High-Credibility Prior Theses (battle-tested, prioritize these)\n" + "\n".join(lines) + "\n"

    # Only inject RAG if similarity is meaningful (score > 0.3)
    knowledge_section = ""
    relevant_chunks = [c for c in knowledge_chunks if c.get("score", 1) > 0.3]
    if relevant_chunks:
        chunks_text = "\n\n---\n\n".join(c["text"] for c in relevant_chunks)
        knowledge_section = f"\n## Relevant Knowledge Base\n{chunks_text}\n"

    return (
        f"## User Profile\n"
        f"- Risk tolerance: {risk}\n"
        f"- Watchlist: {watchlist_str}\n"
        f"{thesis_section}"
        f"{knowledge_section}"
    )
