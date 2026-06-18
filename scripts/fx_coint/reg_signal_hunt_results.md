# FX Regression Signal Hunt (1–4h) — Results & Verdict

**Date:** 2026-06-18
**Script:** `scripts/fx_coint/reg_signal_hunt.py`
**Run:** `--symbol all --freq all` (6 majors × {1h,2h,3h,4h}, Ridge on 5 price-only
features, vol-normalized target, 70/30 temporal split with purge, London+NY
session 07–21 UTC, net of real Pepperstone Razor costs).

## Results table (OOS = held-out 30%)

| pair | freq | N | IC | IC* | clears | BH-sig | netA | netB | netC | nC |
|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 1h | 7171 | 0.0049 | 0.0763 | – | – | -0.775 | -0.875 | -0.724 | 120 |
| EURUSD | 2h | 2606 | 0.0460 | 0.0522 | – | – | -0.587 | -0.560 | -0.285 | 499 |
| EURUSD | 3h | 651 | 0.0570 | 0.0405 | ✓ | – | -0.271 | +0.005 | +1.070 | 133 |
| EURUSD | 4h | 651 | -0.0269 | 0.0392 | – | – | -0.178 | +0.393 | +0.634 | 242 |
| GBPUSD | 1h | 7170 | 0.0113 | 0.0698 | – | – | -0.763 | -0.724 | +2.052 | 60 |
| GBPUSD | 2h | 2606 | 0.0115 | 0.0477 | – | – | -0.813 | -0.896 | +0.373 | 26 |
| GBPUSD | 3h | 651 | -0.0191 | 0.0382 | – | – | -0.989 | -0.788 | +0.329 | 85 |
| GBPUSD | 4h | 651 | -0.0546 | 0.0371 | – | – | +0.052 | +0.054 | +0.665 | 175 |
| AUDUSD | 1h | 7170 | 0.0177 | 0.0991 | – | – | -0.795 | -1.028 | -0.217 | 89 |
| AUDUSD | 2h | 2606 | 0.0174 | 0.0685 | – | – | -1.115 | -1.449 | -5.118 | 78 |
| AUDUSD | 3h | 651 | -0.0388 | 0.0520 | – | – | -0.545 | -1.797 | -6.721 | 10 |
| AUDUSD | 4h | 651 | 0.0090 | 0.0504 | – | – | -2.037 | -1.707 | -1.236 | 127 |
| USDJPY | 1h | 7171 | -0.0024 | 0.0808 | – | – | -0.742 | -0.841 | -0.195 | 693 |
| USDJPY | 2h | 2606 | -0.0066 | 0.0570 | – | – | -0.643 | -0.829 | -0.986 | 618 |
| **USDJPY** | **3h** | **651** | **0.1137** | **0.0426** | **✓** | **✓** | **+0.558** | **+0.639** | **+0.995** | **429** |
| USDJPY | 4h | 651 | 0.0111 | 0.0404 | – | – | -0.941 | -1.393 | -0.697 | 291 |
| USDCHF | 1h | 7171 | 0.0124 | 0.1127 | – | – | -1.134 | -1.579 | -4.614 | 50 |
| USDCHF | 2h | 2606 | 0.0192 | 0.0796 | – | – | -1.437 | -1.679 | -2.286 | 109 |
| USDCHF | 3h | 651 | -0.0279 | 0.0618 | – | – | -1.504 | -2.359 | -3.089 | 119 |
| USDCHF | 4h | 650 | 0.0050 | 0.0592 | – | – | -0.732 | -0.608 | -0.402 | 203 |
| USDCAD | 1h | 7171 | 0.0096 | 0.1438 | – | – | -0.974 | -1.103 | -1.734 | 25 |
| USDCAD | 2h | 2606 | 0.0023 | 0.0965 | – | – | -0.860 | -0.935 | +2.846 | 42 |
| USDCAD | 3h | 651 | 0.0434 | 0.0728 | – | – | -0.717 | +0.130 | +3.048 | 95 |
| USDCAD | 4h | 651 | 0.0051 | 0.0691 | – | – | -0.829 | -0.170 | +2.103 | 35 |

IC-by-hour for cells that clear IC\*: EURUSD 3h → {15: +0.049}; **USDJPY 3h → {15: +0.088}**.

## Go/no-go gate (clears IC\* AND BH-significant AND netC > 0)

- **USDJPY 3h** is the only cell passing all three: IC 0.114 (vs IC\* 0.043),
  BH-significant across the 24-cell family, netA/netB/netC all positive
  (+0.56 / +0.64 / +1.00 bps).
- **EURUSD 3h** clears IC\* and has netC > 0, but is **not** BH-significant — fails the gate.
- All 22 other cells fail.

## Decomposition (gross vs cost vs significance)

- **Most cells fail on GROSS IC, not cost.** At 1h, realized IC is ~0.005–0.018
  against an IC\* of 0.07–0.14 — an order of magnitude short. This is the cost
  wall behaving exactly as predicted: sub-hourly/1h direction is hopeless at
  retail cost regardless of session. 2h is closer (IC ~0.01–0.05 vs IC\* ~0.05–0.10)
  but still short for every pair.
- **The netB/netC columns are noisy, not signal.** Large positive netC values on
  small trade counts (e.g. USDCAD 2h +2.85 on nC=42, GBPUSD 1h +2.05 on nC=60)
  sit alongside large negatives (AUDUSD 3h −6.72 on nC=10). These are
  small-sample artifacts of the cost gate, not evidence of edge — do not read
  them as monetization.

## Verdict: NO-GO as a deployable edge; USDJPY 3h @ 15:00 UTC is a candidate needle

On this evidence the system is **NO-GO**: 23 of 24 cells fail, and the single
survivor carries strong artifact risk:

1. **Tiny sample.** The 3h/4h panels have only N≈651 OOS rows because
   `truncate("3h")` aligns bars to a fixed midnight grid, so within the 07–21
   session only ~4 bars/day survive (entries at 09/12/15/18 UTC). The
   USDJPY 3h signal concentrates at the 15:00 UTC bucket (IC +0.088) — the
   London/NY overlap, consistent with the cost-analysis thesis — but that bucket
   is only ~1/4 of entries (n≈160). One promising hour on ~160 obs is precisely
   the profile of a needle that has died under breadth before
   (cf. the h3/h6 "false needle" in the hourly next-bar work).

2. **1-of-24 with a single 70/30 split.** BH-FDR controls the family, but a
   single split is not walk-forward; the survivor could be a fortunate test window.

**This does not kill the 3h/overlap hypothesis — it flags it for confirmation.**
USDJPY 3h is the first intraday cell to clear its real-cost break-even bar *and*
survive BH, and it does so exactly where the cost math said it could (2–3h hold,
overlap window). Before any GO it needs the established confirmation method:

- Walk-forward (rolling/expanding, multiple folds) instead of one 70/30 split.
- Per-hour-of-day IC stability and sign-stability across folds (is hour-15 robust?).
- Breadth: more years, and whether USDCHF/USDCAD 3h (which clear IC\* on netC but
  not significance) move together with USDJPY under pooling.
- Bucket-alignment sensitivity: re-run with session-anchored 3h bars (entries at
  07/10/13/16/19) to confirm the signal is the overlap and not a fixed-grid artifact.
- If it survives all of the above, tick-exact fill verification before sizing.

**Bottom line:** cost wall confirmed at 1h/2h for all pairs; 3h is the first
horizon where a cell clears, and USDJPY 3h @ the overlap is a genuine,
significance-passing candidate — but on ~160 effective observations it is a
needle to confirm, not an edge to trade.
