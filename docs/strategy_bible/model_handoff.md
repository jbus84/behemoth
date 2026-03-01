# Model Handoff: WFO → Production API

## Monthly Retraining Cycle

The CatBoost model is valid for **exactly one calendar month**. At the start of each new month, you must retrain and deploy.

### Step 1: Run WFO with Model Export

```bash
uv run python scripts/run_tick_opportunity_monthly_wfo.py \
    --config configs/research/governance/oco_rule_universe_registry.yaml \
    --model-export-dir models/oco
```

This produces per symbol:
- `models/oco/EURUSD_model_2026-03.cbm` — serialized CatBoost binary
- `models/oco/EURUSD_model_2026-03.json` — threshold config:
  ```json
  {
    "threshold_exec": 0.72,
    "threshold_source": "rolling_history",
    "execution_quantile": 0.9,
    "features": ["cost_est_pips", "range_pips", ...]
  }
  ```

### Step 2: Hot-Reload the API

```bash
curl -X POST http://127.0.0.1:8000/reload
# Response: {"ok": true, "models_loaded": {"EURUSD": "2026-03", ...}}
```

No restart needed — the API scans `models/oco/` and loads the latest `.cbm` per symbol.

### Step 3: Verify

```bash
curl http://127.0.0.1:8000/health
# Confirm models_loaded shows the new month
```

## Architecture: One Model, Many Candidates

The WFO trains **one CatBoost model per symbol per month**. The structural parameters (`bar_ticks=100`, `horizon∈{5,6}`, `barrier_pips∈{2,3}`) are **features** in the model, not separate models.

At prediction time, the API:
1. Reads `oco_rule_universe_registry.yaml` → 4 candidates per symbol
2. Computes 13 rolling features once (shared across candidates)
3. Sets `horizon` + `barrier_pips` per candidate → runs CatBoost 4×
4. Returns all 4 predictions ranked by `pred_prob` descending
5. Only candidates where `selected_exec=1` (pred_prob ≥ threshold) are actionable

```
POST /predict {"symbol": "EURUSD"}
→ [
    {"candidate_uid": "oco_first_touch_clean|EURUSD|100|h5|b3_from_touch", "pred_prob": 0.81, "selected_exec": 1},
    {"candidate_uid": "oco_first_touch_clean|EURUSD|100|h6|b3_from_touch", "pred_prob": 0.74, "selected_exec": 1},
    {"candidate_uid": "oco_first_touch_clean|EURUSD|100|h5|b2_from_touch", "pred_prob": 0.65, "selected_exec": 0},
    {"candidate_uid": "oco_first_touch_clean|EURUSD|100|h6|b2_from_touch", "pred_prob": 0.58, "selected_exec": 0},
  ]
```

## Startup Flow (cBot)

1. `OnStart()` → call `MarketData.GetTicks()` → POST to `/backfill`
2. Response includes `"warm": true` when 289+ bars loaded
3. `OnTick()` → POST each tick to `/ticks`
4. When a new bar completes → POST to `/predict` → act on any `selected_exec=1`

## Governance Lock

The `oco_rule_universe_registry.yaml` is SHA256-hashed and change-controlled. Any modification requires `OCO-GOV-001` ticket approval. The API loads this registry on startup and uses it to enumerate valid candidates — no silent expansion.
