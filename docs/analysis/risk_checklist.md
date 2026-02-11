# Risk Checklist — Signal/PNL Alignment (M5/M15 MOM)

Date: 2026-02-07

This checklist focuses on **signal/PNL alignment risk** for the rule‑based MOM strategy (single‑leg PnL, spread‑based Z exits) and related operational controls.

---

## 1) Non‑Active Leg Dominance (Exit Attribution)
**What it measures:** how often the **non‑active leg** move is larger than the active‑leg move at exit.

**Current values:**
- **M5:** other‑dominant rate **52.04%**; ratio>0.6 **38.38%**
- **M15:** other‑dominant rate **51.99%**; ratio>0.6 **37.96%**

**Interpretation:** the spread exit is frequently driven by the non‑active leg. This is expected for a single‑leg strategy but should be monitored.

**Concern threshold:**
- **other‑dominant rate > 60%** or **ratio>0.6 > 45%** → review exit logic.

---

## 2) Early‑Exit Penalty (Active‑Leg Improvement After Exit)
**What it measures:** how often active‑leg PnL would have improved **after** Z‑exit within a short window.

**Current values (20‑bar lookahead):**
- **M5:**
  - `delta_gt_5` = **61.57%**
  - `delta_gt_10` = **41.85%**
  - `delta_gt_20` = **21.26%**
- **M15:**
  - `delta_gt_5` = **70.70%**
  - `delta_gt_10` = **56.01%**
  - `delta_gt_20` = **36.25%**

**Interpretation:** Z‑exits often cut off further active‑leg gains. This is a structural trade‑off of Z‑based exits.

**Concern threshold:**
- **delta_gt_10 > 60%** → consider reviewing exit policy or adding active‑leg trailing logic.

---

## 3) Guardrail Skip Rate (Operational Impact)
**What it measures:** how much trade density the guardrail removes.

**Current values:**
- **M5:** keep 34,959 / 221,217 → **84.20% skipped**
- **M15:** keep 27,090 / 73,629 → **63.21% skipped**

**Interpretation:** guardrail materially reduces exposure; must be acceptable for deployment.

**Concern threshold:**
- **skip rate > 90%** → re‑evaluate streak length or cooldown duration.

---

## 4) PnL‑Based Reporting (Policy Check)
**Requirement:** all performance stats and guardrail logic must use **PnL sign**, not `outcome` labels.

**Status:** PASS (manual and diagnostics use `pnl_bps > 0`).

---

## Evidence Files
- Exit attribution summaries:
  - `data/analysis/m5_exit_attribution_summary.csv`
  - `data/analysis/m15_exit_attribution_summary.csv`
- Exit penalty summaries:
  - `data/analysis/m5_exit_penalty_summary.csv`
  - `data/analysis/m15_exit_penalty_summary.csv`
- Guardrail diagnostics:
  - `data/analysis/m5_guardrail_overall.csv`
  - `data/analysis/m15_guardrail_overall.csv`
