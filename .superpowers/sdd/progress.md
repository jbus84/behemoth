# BoostLSS Jump-Diffusion & SHASH Distribution Comparison — SDD progress

Base: 18637d03867cf17b1c383c7180b7c6ace6b1c4e0
Plan: docs/superpowers/plans/2026-07-02-boostlss-jump-distributions.md

Prior plan (BoostLSS XS Anomaly Detection + Meta-Labeler) completed and merged;
its ledger history is preserved in git log if needed.

- Task 1: complete (commit 6a81ccd7, review clean; boostlss bumped 6b9924ea..5b22552f, Merton/SHASH import+fit+predict verified)
- Task 2: complete (commit b6c0e7b4, review clean; NLL formulas for merton+shash independently verified numerically by reviewer; correct import style for Task 3 confirmed by controller as bare `from distributions import ...` (sibling import, sys.path auto-includes script dir under `uv run python scripts/boostlss_xs/X.py` invocation) — implementer's report claim of `scripts.boostlss_xs.distributions` prefix does NOT apply)
- Task 3: complete (commit 9d9eb343, review clean; EURUSD gaussian smoke test +1.381 bps/fill matches PR #374 reference; sizing sigma clip untouched/behavior-preserving confirmed by reviewer; KNOWN ISSUE for Task 4: oos_nll can be `inf` on early WFO folds (unclipped sigma overflow, pre-existing, non-regressive) — Task 4 must filter non-finite fold_nll values before averaging, or the comparison table's gaussian NLL column will show inf)
