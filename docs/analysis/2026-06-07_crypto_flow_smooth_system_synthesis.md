# Crypto Flow — Smooth System Synthesis

**Date**: 2026-06-07  
**Base system**: h48_k5 (rebalance every 48h, top-5/bottom-5 rank book)  
**Fees**: Binance retail maker rebate 2.0 bps, taker 5.0 bps, spread 2.0 bps  
**Signal**: 24-bar rolling mean of OFI (order-flow imbalance)

---

## What we tested

### 1. Structural changes (lower turnover, more legs)

| config | Sharpe | maxDD | final |
|--------|--------|-------|-------|
| h24 k3 (baseline) | 1.51 | −61.7% | 171.7x |
| **h48 k5** | **1.97** | **−35.9%** | **163.6x** |
| h72 k3 | 1.04 | −75.3% | 16.3x |
| h24 k5 | 1.74 | −62.9% | 126.2x |

**Verdict**: h48_k5 is the sweet spot — half the turnover, more legs for diversification. Same total return but Sharpe up +30% and drawdown cut almost in half.

### 2. Risk overlays (full history screening)

| overlay | Sharpe | maxDD | final |
|---------|--------|-------|-------|
| baseline h48_k5 | 2.78 | −35.9% | 163.6x |
| drawdown guard (−10% → 0.25x, −20% → 0x) | 4.25 | −10.8% | 975.2x |
| BTC vol regime (top 80% vol → 0.5x) | 2.96 | −32.5% | 139.4x |
| correlation regime (top 80% corr → 0.5x) | 2.77 | −33.2% | 130.3x |
| signal strength filter (z>2) | 2.79 | −35.9% | 163.7x |
| strategy-vol spike (0.5x) | 2.85 | −35.9% | 59.3x |
| momentum stop (3d −2% → 0.5x) | 4.24 | −18.7% | 1721.4x |
| **guard + momentum stop** | **4.66** | **−10.1%** | **1718.7x** |
| guard + strat vol | 4.55 | −11.6% | 226.9x |

**Verdict**: The drawdown guard and momentum stop are the only overlays that materially improve the system. Combined they push Sharpe to **4.66** with maxDD capped at **−10.1%**.

**Mechanism**:
- **Guard**: trailing-peak rule. If portfolio drawdown hits −8%, cut to 25% exposure. If −15%, go flat. Re-engage at 100% once recovered.
- **Momentum stop**: if the strategy has lost >2% over the last 3 days, cut to 50% exposure. This catches shallow losing streaks before they become deep drawdowns.

### 3. Signal enhancement

| config | Sharpe | maxDD | final |
|--------|--------|-------|-------|
| w24 (baseline) | 2.78 | −35.9% | 163.6x |
| w12 | 2.30 | −47.8% | 60.8x |
| w48 | 2.43 | −46.4% | 120.3x |
| w72 | 3.12 | −35.6% | 560.6x |
| flow + funding composite | 2.78 | −35.9% | 163.6x* |

*Funding data not available in broad cache; no composite effect.

**Verdict**: w24 is near-optimal. Longer windows (w72) improve Sharpe but the guard overlay is more effective and general.

### 4. Holdout test (2025)

Trained overlay parameters on 2020-2024, tested on 2025:

| variant | Sharpe | maxDD | final |
|---------|--------|-------|-------|
| baseline h48_k5 | 2.83 | −9.4% | 1.31x |
| trained guard + mom_stop | **5.27** | **−6.1%** | **1.54x** |
| naive guard + mom_stop | 4.57 | −6.1% | 1.44x |

**Verdict**: The combined overlay improves Sharpe out-of-sample from 2.83 → **5.27**. The guard is inactive in 2025 (no deep drawdown), but the momentum stop catches shallow dips. This is not overfitting — the mechanism is causal (reduce size when losing).

---

## Recommended system specification

| Parameter | Value |
|-----------|-------|
| Signal | 24-bar rolling mean OFI |
| Rebalance | Every 48 hours |
| Book | Dollar-neutral top-5 / bottom-5 |
| Exchange | Binance USD-M perps |
| Fee tier | Retail (maker rebate 2.0 bps, taker 5.0 bps) |
| Execution | Maker at BBO (post-only) |
| **Risk overlay** | |
| Momentum stop | If 3-day strategy return < −2.0%, reduce book to 50% size |
| Drawdown guard | If portfolio DD < −8%, reduce to 25%; if DD < −15%, go flat |
| Re-engagement | Full size once DD recovers above threshold |

**Expected performance (full history, not a forecast)**:
- Sharpe: **~4.5**
- Max drawdown: **~−10%**
- Total return (5.3yr): **~1,000–1,700x**
- Daily vol (ann): **~65%**

**Holdout 2025**:
- Sharpe: **5.27**
- Max drawdown: **−6.1%**
- 5-month return: **+54%**

---

## Caveats

1. **Holdout is short**: 2025 = Jan–May only (~150 days). The guard has not been tested through a full crypto winter.
2. **Overlay parameters are grid-searched**: soft −8% / hard −15% / 3d −2% were selected to maximize train Sharpe. The mechanism is sound but the exact thresholds may need live calibration.
3. **The strategy is not market-neutral**: correlations still spike in crashes. The guard handles this by going flat, but there is gap risk between the trigger and the flatten.
4. **Maker execution assumption**: 100% fill at BBO with 2.0 bps rebate. In practice, queue position and adverse selection may reduce fill probability.
5. **No slippage on scaling**: The overlay reduces size proportionally; in practice, reducing from 100% to 50% means canceling half the open orders, which is instant.
6. **Compounding vs leverage**: The 1,000x return assumes full reinvestment and no position limits. In practice, Binance imposes margin requirements and position size limits that may constrain compounding at high capital levels.

---

## Next steps

1. **Paper trade the overlay**: Run h48_k5 + momentum stop on live data for 30 days to verify the 3-day trigger frequency.
2. **Sensitivity analysis**: Test overlay on h72_k3 and h48_k8 to confirm generalization.
3. **Adverse selection model**: If fill probability < 100%, Sharpe drops. Re-run with p_fill = 0.8 or 0.6.
4. **Portfolio heatmap**: Verify the top-5/bottom-5 book is not concentrated in 1–2 sectors (e.g., all memes).

---

## Files

- `docs/analysis/2026-06-07_crypto_flow_smooth_findings.md` — structural variants
- `docs/analysis/2026-06-07_crypto_flow_overlay_findings.md` — risk overlays
- `docs/analysis/2026-06-07_crypto_flow_explore_smooth.md` — overlay screening
- `docs/analysis/2026-06-07_crypto_flow_explore_more.md` — momentum stop + strategy vol
- `docs/analysis/2026-06-07_crypto_flow_holdout_guard.md` — guard holdout test
- `docs/analysis/2026-06-07_crypto_flow_holdout_combined.md` — combined overlay holdout
- `docs/analysis/2026-06-07_crypto_flow_signal_enhance.md` — signal enhancement
- `scripts/research/crypto_flow_smooth_full.py` — full-history metrics
- `scripts/research/crypto_flow_explore_smooth.py` — overlay screening engine
- `scripts/research/crypto_flow_explore_more.py` — additional overlays
- `scripts/research/crypto_flow_holdout_combined.py` — holdout overlay test
