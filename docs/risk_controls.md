# Risk Controls

Risk controls are **hard gates** enforced at the API boundary.

## Guardrail (per‑pair)
- **Loss‑streak**: default 3
- **Cooldown**: default 7 days
- **Trigger**: `pnl_bps <= 0`

## Account Kill‑Switches

| Control | Default | Meaning |
|---|---|---|
| Max daily loss | 5% | Floating vs day‑start equity |
| Max drawdown | 10% | Floating vs peak equity |
| Max consecutive losses | 5 | Count of consecutive negative closes |

If any trigger fires, the account is **halted** and new positions are rejected until reset.

## Sizing & Exposure

| Control | Default |
|---|---|
| Max total exposure | 100% of equity |
| Per‑pair cap | 10% of equity |
| Weight overshoot | +10% over target |

Target notional per pair is computed from `configs/pair_weights.yaml`.  
Pairs with higher weights get a larger share of exposure.

## Reset

Use `POST /risk/{strategy_id}/reset` to clear a halt after manual review.
