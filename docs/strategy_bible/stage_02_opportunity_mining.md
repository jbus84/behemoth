# Stage 2 - Opportunity Mining

## Objective
Mine high-count, gross-positive OCO opportunity families as hypotheses before model filtering and robustness controls.

## Inputs
- Candidate catalogs:
- `data/analysis/tick_opportunity_mining/<SYMBOL>_oco_candidates.csv`
- Key candidate fields:
- `selection_pass`, `annualized_test_fills`, `mean_gross_pips_test`, `family`, `state_id`, `bar_ticks`, `horizon`

## Process
- Enumerate OCO state families and horizons.
- Keep broad candidate frontier (`selection_pass`) for downstream filtering.
- Compute concentration/smoothness diagnostics (`M01-M03`).

## Exact Calculations
- `edge_weight = annualized_test_fills * mean_gross_pips_test`
- `M01_top3_contrib_share = sum(top3 edge_weight by state block) / sum(all edge_weight)`
- `M02_smoothness_abs_jump = median(abs(diff(mean_gross_pips_test across adjacent horizon)))`
- `M03_positive_density = mean(mean_gross_pips_test > 0 among selection_pass)`

## Causality / Leakage Controls
- Mining outputs are hypothesis-generation only.
- No deployment gating at this stage without downstream WFO/robustness confirmation.

## Failure Modes
- Edge concentration in very few states (fragile alpha).
- Non-smooth parameter surfaces indicating noisy search.
- Post-hoc over-interpretation without Stage 3/8 controls.

## Interpretation Guide
- Lower `M01` is better diversification.
- Lower `M02` indicates smoother, less brittle parameter landscape.
- Higher `M03` indicates a denser positive frontier.

## Validation Gates
- Informational at Stage 2.
- Hard pass/fail occurs later via Stage 3, Stage 7, Stage 8.

## Canonical Analysis Reports
- `docs/analysis/eurusd_tick_opportunity_mining_report.md`
- `docs/analysis/gbpusd_tick_opportunity_mining_report.md`
- `docs/analysis/usdjpy_tick_opportunity_mining_report.md`

## Reproduction Commands
```bash
uv run python scripts/run_tick_opportunity_mining.py \
  --config configs/research/experiments/eurusd_tick_opportunity_mining.yaml
```

## Traceability
- `scripts/run_tick_opportunity_mining.py`
- `docs/analysis/*_tick_opportunity_mining_report.md`
- `docs/strategy_bible/generated/stage_02_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_02:START -->
### Auto Snapshot - Stage 02

- generated_at: `2026-02-27 12:15:07 UTC`
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Key Results
| symbol   |   candidates_total |   selected_total |   selected_mean_gross_pips |   selected_median_annualized |   m01_top3_contrib_share |   m02_smoothness_abs_jump |   m03_positive_density |
|:---------|-------------------:|-----------------:|---------------------------:|-----------------------------:|-------------------------:|--------------------------:|-----------------------:|
| EURUSD   |               2160 |              737 |                    1.19563 |                      15514.1 |                0.0486952 |                 0.0940589 |                      1 |
| GBPUSD   |               2160 |              762 |                    1.22153 |                      18903.7 |                0.0508144 |                 0.0744663 |                      1 |
| USDJPY   |               2160 |              995 |                    1.92264 |                      20211.8 |                0.04021   |                 0.0981752 |                      1 |

#### Plots
![stage_02_selected_scatter](../figures/oco_bible/stage_02_selected_scatter.png)

#### Edge Contribution by State Block
| symbol   | family                | state_id                                  |   bar_ticks |   horizon |   edge_weight |   contrib_share |
|:---------|:----------------------|:------------------------------------------|------------:|----------:|--------------:|----------------:|
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         6 |        273060 |      0.0197535  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         5 |        225779 |      0.0163332  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         4 |        174293 |      0.0126086  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2   |         100 |         6 |        155374 |      0.01124    |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2 |         100 |         6 |        145548 |      0.0105291  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3            |         100 |         6 |        143860 |      0.010407   |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2 |         100 |         5 |        124395 |      0.00899893 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2   |         100 |         5 |        121071 |      0.00875842 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         6 |        316345 |      0.0189299  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         5 |        266813 |      0.015966   |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2   |         100 |         6 |        266020 |      0.0159185  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2   |         100 |         5 |        224246 |      0.0134188  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         4 |        209899 |      0.0125602  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2   |         100 |         6 |        191214 |      0.0114421  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3            |         100 |         6 |        180164 |      0.0107809  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2   |         100 |         4 |        175963 |      0.0105295  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         6 |        605018 |      0.0154148  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         5 |        531927 |      0.0135526  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         4 |        441263 |      0.0112426  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3            |         100 |         6 |        426780 |      0.0108736  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2   |         100 |         6 |        385493 |      0.00982171 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3            |         100 |         5 |        338588 |      0.00862664 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2   |         100 |         5 |        336760 |      0.00858006 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2            |         100 |         3 |        330929 |      0.00843151 |

#### Overfitting Diagnostics (Downstream, Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| EURUSD   |        0.9 | 325515 |        9 |                 9 |                      1.02232 |                              nan |                                      nan |             1.15261e-09 |         1.15261e-09 |     1.15261e-09 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 | 414128 |        9 |                 9 |                      1.00211 |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 | 459585 |        9 |                 9 |                      1.36145 |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.
- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation.
<!-- GENERATED:STAGE_02:END -->
