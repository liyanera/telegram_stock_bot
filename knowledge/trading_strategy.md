# AI Industry Trading Strategy

## Investment Mandate

$1M paper trading account focused on the AI industry ecosystem.
Target: best risk-adjusted return over a 6-12 month horizon.
Mandate: fully invested at all times — deploy all cash, target $0 residual cash.
Residual cash > $5,000 after rebalancing means insufficient deployment.

## 5-Pillar Universe

The portfolio is structured around 5 pillars of the AI industry ecosystem:

**Data Center Infrastructure (target 40-50% of portfolio)**
Key names: NVDA, AMD, AVGO, ANET, MRVL, SMCI, ARM, MSFT, GOOGL, META, AMZN
Rationale: backbone of AI compute — GPU, networking, hyperscaler capex

**Memory & Semiconductor Equipment — HBM focus (target 15-20%)**
Key names: MU, LRCX, KLAC, AMAT, ASML
Rationale: HBM demand tied directly to AI GPU production volumes

**AI Power & Energy Infrastructure (target 15-20%)**
Key names: CEG, VST, TLN, NEE, NRG, OKLO, SMR
Rationale: low-beta diversifier — AI data center power demand is multi-year secular trend

**Photonics, Optical & Interconnects (target 10-15%)**
Key names: COHR, CIEN, LITE, VIAV
Rationale: optical interconnects are the bandwidth bottleneck inside and between data centers

**AI Software & Platform — supporting (target 0-10%)**
Key names: PLTR, CRWD, NET, DDOG, NOW, CRM
Rationale: optional allocation; only when software names show stronger risk-adjusted opportunity

## Risk-Adjusted Sizing (Beta-Adjusted)

Position sizing is adjusted by beta to control portfolio volatility:
- Base position size = target_weight / beta
- Example: want 15% exposure in NVDA (β=1.8) → actual allocation = 15/1.8 = 8.3%
- Energy names (CEG β=0.8) can be sized up to 20% due to low beta
- High-beta names (SMCI β=2.0, OKLO β=2.5) capped at 5-7%
- Target portfolio beta ≤ 1.3 for Sharpe optimization

## Dual-Plan Rebalancing

**Pre-Open (9:20 AM ET / 13:20 UTC)**
- Fundamental + macro driven positioning
- Uses previous day closing prices as cost basis
- 6-12 month conviction lens: earnings revisions, valuation, technical structure
- Larger position changes, sector allocation decisions

**Pre-Close (3:30 PM ET / 19:30 UTC)**
- Intraday momentum refinement using real-time prices
- Rules: trim names down >3% without news, add names up >2% with volume
- Smaller adjustments: 5-15% position changes, not wholesale rebuilds
- Respects daily and weekly turnover limits

## Portfolio Constraints

- Maximum 10 positions
- Maximum 20% of portfolio per single name
- Daily turnover ≤ 10% of GMV
- Weekly turnover ≤ 40% of GMV
- Minimum trade notional: $5,000 (ignore smaller trades)

## Selection Criteria (6-12 Month Horizon)

1. Strongest secular AI tailwind within their pillar
2. Earnings revision momentum (analyst upgrades > downgrades)
3. Reasonable valuation relative to growth (PEG < 2.0 preferred)
4. Technical structure: prefer names above SMA200
5. Avoid overlapping factor exposure to reduce correlation across positions
