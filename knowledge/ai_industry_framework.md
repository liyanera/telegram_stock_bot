# AI Industry Investment Framework — 4 Pillars

## Pillar 1: Data Center Infrastructure

### Key Players
- NVDA: GPU monopoly for AI training/inference, H100/H200/B200 Blackwell cycle
- AMD: MI300X gaining enterprise AI traction, challenger to NVDA
- AVGO: Custom ASIC (Google TPU, Meta MTIA), data center networking (Tomahawk)
- ANET: Ethernet switching for AI clusters, 400G/800G upgrade cycle
- MRVL: Custom silicon (Amazon Trainium/Inferentia), PCIe switches, coherent DSPs
- SMCI: AI server systems integrator, highest NVDA GPU density
- ARM: CPU architecture royalties in every AI chip, edge AI silicon

### Key Metrics
- Data center revenue as % of total (want >50% for pure play)
- Gross margin trend (AI mix should be accretive for fabless)
- Customer concentration risk (hyperscaler dependency)
- Lead times and backlog as forward demand signal
- Hyperscaler capex guidance (MSFT/GOOG/META/AMZN) = proxy demand

### Valuation Framework
- NVDA: 30-40x forward earnings justified by monopoly AI GPU position
- AVGO: 25-30x forward, reliable compounder with custom silicon tailwind
- ANET: 35-45x forward, network upgrade cycle is multi-year

---

## Pillar 2: Memory — HBM as the AI Bottleneck

### Key Players
- MU (Micron): US leader in HBM3E, primary beneficiary of AI memory demand
- LRCX (Lam Research): Etch equipment critical for HBM stacking
- KLAC (KLA): Process control for advanced memory manufacturing
- AMAT (Applied Materials): Deposition equipment for DRAM/HBM

### Investment Thesis
HBM (High Bandwidth Memory) is the critical bottleneck for AI GPUs.
Each NVDA H100 uses 80GB HBM3, B200 uses 192GB HBM3E.
HBM capacity is constrained — only SK Hynix, Micron, Samsung can produce it.
Micron (MU) is the only US-listed pure-play HBM exposure.

### Key Metrics for MU
- HBM revenue guidance and ASP trends
- DRAM bit growth vs. pricing
- Capital intensity (HBM requires 3x the capex per bit vs standard DRAM)
- Inventory cycle position (leading indicator of earnings trajectory)

### Risk: Memory is cyclical
- DRAM/NAND commodity cycles can overwhelm HBM tailwind in down-cycles
- MU Beta ~1.4 — size positions accordingly for risk-adjusted returns

---

## Pillar 3: Energy — AI's Hidden Infrastructure

### Investment Thesis
AI data centers are power-hungry: a single GB200 NVL72 rack consumes 120kW.
US data center power demand projected to triple by 2030.
Nuclear power is uniquely positioned: 24/7 baseload, zero carbon, near data centers.
Power constraint = rate-limiting factor for AI infrastructure buildout.

### Key Players
- CEG (Constellation Energy): Largest US nuclear operator, direct data center PPAs
  - Signed 20-year Microsoft deal for Three Mile Island restart
  - Trades at premium to utilities for AI power optionality
- VST (Vistra Energy): Diversified power including nuclear, volatile but high beta to power prices
- TLN (Talen Energy): Pure-play nuclear + data center co-location (Amazon deal)
- NEE (NextEra): Largest renewable energy, wind/solar for data centers
- SMR (NuScale): Small modular reactor, long-dated speculative play

### Key Metrics
- Power purchase agreement (PPA) announcements with hyperscalers
- Nuclear capacity factor and fuel costs
- Regulatory approvals for restarts/new builds
- Data center co-location capacity additions

### Risk Profile
- CEG/VST have lower correlation to tech sector = good diversifier
- Power prices volatile — weather and natural gas dependency
- Regulatory risk for nuclear restarts

---

## Pillar 4: Photonics & Optical — The Interconnect Layer

### Investment Thesis
AI clusters require massive inter-GPU bandwidth.
A 100,000 GPU cluster needs ~10M optical transceivers.
800G/1.6T optics are the new capacity constraint.
Co-packaged optics (CPO) is the next architectural shift.

### Key Players
- COHR (Coherent): #1 optical components, transceiver market leader
  - Direct exposure to 800G/1.6T data center transceiver upgrade cycle
  - Also industrial/telecom diversification
- CIEN (Ciena): Optical networking systems, WaveLogic coherent technology
- ANET: Also benefits from optics (sells systems that use optical transceivers)
- LITE (Lumentum): Optical components including EMLs for transceivers
- VIAV (Viavi): Test & measurement for optical networks

### Key Metrics
- 800G/1.6T transceiver shipment volumes and ASP trends
- Hyperscaler optical capex in earnings calls
- Co-packaged optics (CPO) design wins timeline
- Yield rates for advanced optical components

### Risk Profile
- COHR: Higher beta (~1.5), volatile, but direct AI optics exposure
- Supply chain constraints on indium phosphide (InP) substrates
- Customer concentration (top 5 hyperscalers = majority of revenue)

---

## Portfolio Construction for Risk-Adjusted Returns (6-12 Month Horizon)

### Target Allocation by Pillar
| Pillar | Target Weight | Rationale |
|--------|--------------|-----------|
| Data Center Infra | 45-50% | Largest addressable market, clearest AI monetization |
| Memory (HBM) | 15-20% | Constrained supply, price power, cyclical hedge needed |
| Energy | 15-20% | Low tech correlation, structural AI demand, diversifier |
| Photonics/Optical | 10-15% | High growth, but more speculative/volatile |

### Risk-Adjusted Sizing Rules
- Low beta (<1.0): CEG, NEE, MSFT → can size larger (up to 20%)
- Mid beta (1.0-1.3): NVDA, AVGO, ANET → standard sizing (10-15%)
- High beta (>1.4): MU, COHR, SMCI, AMD → size smaller (5-10%)
- Use beta-adjusted position sizing: target_weight = base_weight / beta

### Sharpe Ratio Optimization Principles
1. Diversify across pillars — low inter-pillar correlation improves Sharpe
2. Energy stocks (CEG) have ~0.3 correlation to tech = valuable diversifier
3. Avoid doubling up on correlated names (e.g., NVDA + AMD + SMCI all move together)
4. Rebalance when any single name exceeds 20% of portfolio due to price appreciation
5. Trim high-beta winners aggressively — they drag down Sharpe in drawdowns

### Catalyst Calendar (6-12 Month Horizon)
- Q2 earnings (Jul-Aug): NVDA, AMD, MU, ANET, CEG, COHR — key re-rating events
- NVDA GTC conference: GPU product launches, partnership announcements
- Hyperscaler capex guidance: MSFT/GOOG/META/AMZN earnings = demand signal
- Nuclear regulatory decisions: NRC approvals for restarts = CEG catalyst
- 800G/1.6T volume ramp: COHR, LITE shipment data in quarterly reports
