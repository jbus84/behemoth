# Daily tail-long claim — validation note

## What was claimed

An exploration in the `behemoth-tail-wfo` line escalated a daily (1d) EURUSD+GBPUSD
long-top-q signal from a NO-GO to a **"behavioral GO"**: pooled q0.85 ≈ +9.2 bps/trade,
both ERA halves positive (+11.8 / +6.1), "no negative quarter ever", max DD survivable.
The escalation happened across several turns under reasonable user pushback (p<0.05 is
the wrong bar for tiny finance signals; execution is Pepperstone Razor, not Dukascopy).

## What an independent rebuild found (`validate_daily_tail.py`)

Rebuilt from scratch with honest, heavy-tail-robust inference. **Verdict: real-but-
negligible — a weak long-momentum tilt statistically indistinguishable from zero. NOT a GO.**

- **R1** — the monotonic mean-vs-q reproduces, but it is *variance, not confidence*: a
  day-block bootstrap 95% CI **includes zero at every q** (q0.85 [−7.7, +19.1], P(mean≤0)≈0.21);
  day-clustered p≈0.5. The clean build yields +5.75, not +9.23 (the original cost was understated).
- **R3** — applying the *same* rule to all 6 majors: 4/6 positive, heterogeneous, with
  **USDCHF (5/5 years) stronger than EURUSD**. This demolishes the "USD-factor / discriminating-
  forecast" story; "EUR+GBP q0.85" is a multiplicity pick from ~30 cells (5 q × 3 pairs × 2 freq).
- **R4** — the one genuine positive: the Ridge selection beats both naive-long (−2.1) and pure
  raw-momentum (−0.1) at +5.75 — the model adds over drift — but still inside a zero-spanning CI.

## Caveat on the framing (why the "GO" read was over-optimistic)

The escalation was driven by selectively favourable readings of a small sample, not new evidence:

1. **Monotonicity-in-q is not robustness.** Any weak ranker shows rising mean as you tighten the
   gate — because you concentrate on higher-conviction *and higher-variance* trades. The bootstrap
   CI widens with q and keeps including zero; P(mean≤0) barely moves (0.25→0.18).
2. **Path stats on ~130 post-selection trades are not evidence.** "No negative quarter / both ERA
   halves positive" is computed on the very cell that was selected from the sweep; it has no
   held-out confirmation, and the signal *did* catch the single worst −375 bps day.
3. **The cell was cherry-picked.** The winning pair/q/freq combination is one of ~30; USDCHF would
   have been the "best" cell on the same logic. In-sample cell selection from a sweep requires a
   genuinely held-out test before any GO.
4. **It would conflict with the only surviving FX edge.** A daily *momentum*-long contradicts the
   weekly *mean-reversion* signal that is the one robustly-surviving edge in this program.

The user's two corrections were both correct and are honoured here: p<0.05 is the wrong bar for
tiny finance signals, and Pepperstone-Razor cost (commission-dominated, ~0.7 bps) clears the gross
easily. The signal fails on **power, robustness, and frequency** — not on p-value reflex.

## Bottom line

Surviving FX edge = **weekly+ mean-reversion only**. The daily tail-long is a faint, real,
model-driven momentum tilt that is too underpowered, too cell-selected, and too low-frequency
(~15 trades/yr) to deploy or to treat as confirmed.
