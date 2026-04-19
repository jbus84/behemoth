"""Parity check implementations — imported for side effect (register_check)."""
from behemoth.parity.checks import (
    core_entries_allowed_vs_readiness,  # noqa: F401
    core_predict_cycles_per_bar,  # noqa: F401
    core_tick_seq_monotonic,  # noqa: F401
    failure_predict_422_warmup_only,  # noqa: F401
    failure_tick_batch_599_fallback,  # noqa: F401
    lifecycle_active_oco_reconciled,  # noqa: F401
    risk_gov_governance_lock_pin,  # noqa: F401
    risk_gov_live_deployable_lock_present,  # noqa: F401
    time_data_bar_close_ts_sorted,  # noqa: F401
)
