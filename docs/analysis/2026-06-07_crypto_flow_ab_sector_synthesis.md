# Crypto Flow — Adverse Selection & Sector Check Synthesis

**Date**: 2026-06-07  
**Base system**: h48_k5 + combined overlay (guard + momentum stop)

---

## A. Adverse-selection stress-test

**Question**: Does the edge survive if maker fills are imperfect and adverse selection eats into each fill?

**Grid tested**: p_fill_base ∈ {1.0, 0.9, 0.8, 0.7, 0.6, 0.5} × adv_bps ∈ {0.0, 0.3, 0.6, 1.0, 1.5, 2.0}

### Results (smoothed system, full history 2020-2025)

| p_fill | adv | baseline Sharpe | baseline maxDD | baseline final | smooth Sharpe | smooth maxDD | smooth final |
|--------|-----|-----------------|----------------|----------------|---------------|--------------|--------------|
| 1.0 | 0.0 | +2.78 | −35.9% | 163.6x | **+5.00** | **−7.9%** | **2101.1x** |
| 1.0 | 1.0 | +2.64 | −37.1% | 121.7x | +4.87 | −8.2% | 1636.4x |
| 0.8 | 0.0 | +2.59 | −37.6% | 108.1x | +4.70 | −8.2% | 1179.8x |
| 0.8 | 1.0 | +2.48 | −38.5% | 85.3x | +4.58 | −8.1% | 934.3x |
| 0.6 | 0.0 | +2.39 | −39.1% | 71.4x | +4.50 | −8.1% | 794.0x |
| 0.6 | 1.0 | +2.31 | −39.8% | 59.8x | +4.42 | −7.8% | 672.1x |
| 0.5 | 0.0 | +2.29 | −39.9% | 58.0x | +4.42 | −7.8% | 673.5x |
| **0.5** | **2.0** | **+2.15** | **−41.0%** | **43.1x** | **+4.34** | **−7.9%** | **506.5x** |

### Verdict

**The edge survives the full grid.** Even with only **50% maker fill probability** and **2.0 bps adverse selection per fill**, the smoothed system still delivers:
- Sharpe **+4.34**
- Max drawdown **−7.9%**
- Total return **506.5x**

**Why?** The structural economics are favorable:
- Maker rebate (2.0 bps) + low turnover (48h) = tiny all-in cost even with partial taker fills
- The gross edge is large enough that cost degradation is a second-order effect
- The overlay compresses drawdown regardless of cost model

**Practical translation**: If you get maker fills 70–80% of the time with modest adverse selection (<1 bps), you are in the +4.5 Sharpe / −8% maxDD zone. Even pessimistic execution (50% fills, 2 bps slippage) still yields +4.3 Sharpe.

---

## B. Sector concentration check

**Question**: Is the top-5/bottom-5 book genuinely diversified, or does it concentrate in one sector?

**Method**: Heuristic sector mapping (major, L1, defi, L2, meme, legacy, alt, other) + sector-Herfindahl index per rebalance.

### Results

| metric | value |
|--------|-------|
| Mean sector-HHI per rebalance | **0.447** |
| Rebalances with HHI > 0.5 | **382 / 987 (38.7%)** |
| Months with max HHI > 0.5 | **56 / 65 (86.2%)** |
| Max single-rebalance HHI | **1.000** (all 10 legs in one sector) |

**Sector distribution**:

| sector | legs | share |
|--------|------|-------|
| other | 5794 | 59.1% |
| defi | 1166 | 11.9% |
| L1 | 785 | 8.0% |
| alt | 748 | 7.6% |
| legacy | 573 | 5.8% |
| major | 535 | 5.5% |
| meme | 205 | 2.1% |

**Most frequent longs**: XMR (362×), BTC (312×), TRX (208×), ETH (194×), MKR (181×)  
**Most frequent shorts**: DASH (172×), MKR (146×), COTI (146×), ZEC (140×), COMP (135×)

### Verdict

**Concentration risk is real.**

- 39% of rebalances have >50% of legs in a single sector
- 86% of months see at least one highly concentrated rebalance
- The "other" category at 59% masks the true picture — many of these are small-cap altcoins that likely share beta to BTC during risk-off

**The high HHI means the book is not a true 10-leg diversifier.** In calm markets the legs are decorrelated; in crashes they likely move together, which is exactly why the drawdown guard is essential.

**Heuristic limitation**: The "other" bucket is large because many altcoins don't fit obvious sector labels. A more rigorous check would use CoinMarketCap sector tags or correlation clustering. The HHI metric itself is robust regardless of labeling.

---

## Combined implications

1. **Execution risk is low**: The system is robust to realistic maker degradation. Even pessimistic assumptions keep Sharpe above 4.0.
2. **Concentration risk is high**: The 10-leg book frequently clusters in one sector. The drawdown guard is not a nice-to-have — it is the primary defense against correlation-spike crashes.
3. **Sector overlay candidate**: A future enhancement could add a sector-dispersion filter — refuse to trade if the top-5 and bottom-5 would put >60% of the book in one sector. This would raise HHI but may sacrifice edge.

---

## Files

- `docs/analysis/2026-06-07_crypto_flow_adverse_selection.md` — full p_fill × adv_bps grid
- `docs/analysis/2026-06-07_crypto_flow_sector_check.md` — sector counts, HHI, symbol frequencies
- `scripts/research/crypto_flow_adverse_selection.py` — stress-test engine
- `scripts/research/crypto_flow_sector_check.py` — concentration checker
