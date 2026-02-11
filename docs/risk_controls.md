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
| Max daily loss buffer | 0.5% | Halt if within buffer of max daily loss |
| Max drawdown | 10% | Floating vs peak equity |
| Max drawdown buffer | 0.5% | Halt if within buffer of max drawdown |

If any trigger fires, the account is **halted** and new positions are rejected until reset.

## Reset

Use `POST /risk/{strategy_id}/reset` to clear a halt after manual review.

## Manual Halt/Resume

- `POST /risk/{strategy_id}/halt` with an optional reason.
- `POST /risk/{strategy_id}/resume` to continue trading.
