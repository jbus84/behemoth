"""Assert the inventory markdown and the check registry agree on surface_ids."""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from behemoth.parity import checks as _checks_pkg  # noqa: F401 — triggers registration
from behemoth.parity import registry

INVENTORY = Path("docs/analysis/2026-04-17-jforex-python-parity-assessment.md")
_HARNESS_LINE_RE = re.compile(r"^\s*-\s*\*\*harness_check:\*\*\s*yes\s*—\s*([\w.]+)")


@pytest.fixture(autouse=True, scope="module")
def _ensure_checks_registered():
    """Re-register all checks before this module runs.

    test_registry.py calls clear_for_tests() and leaves the registry empty.
    Python module caching means re-importing _checks_pkg is a no-op once it
    has been imported. We must reload each sub-module so the @register_check
    decorators fire again.
    """
    import behemoth.parity.checks.core_entries_allowed_vs_readiness as m0
    import behemoth.parity.checks.core_predict_cycles_per_bar as m1
    import behemoth.parity.checks.core_tick_seq_monotonic as m2
    import behemoth.parity.checks.failure_predict_422_warmup_only as m3
    import behemoth.parity.checks.failure_tick_batch_599_fallback as m4
    import behemoth.parity.checks.lifecycle_active_oco_reconciled as m5
    import behemoth.parity.checks.risk_gov_governance_lock_pin as m6
    import behemoth.parity.checks.risk_gov_live_deployable_lock_present as m7
    import behemoth.parity.checks.time_data_bar_close_ts_sorted as m8

    registry.clear_for_tests()
    for mod in (m0, m1, m2, m3, m4, m5, m6, m7, m8):
        importlib.reload(mod)


def _referenced_check_ids() -> set[str]:
    refs: set[str] = set()
    for line in INVENTORY.read_text().splitlines():
        m = _HARNESS_LINE_RE.match(line)
        if m:
            refs.add(m.group(1))
    return refs


def test_every_referenced_check_is_registered() -> None:
    refs = _referenced_check_ids()
    registered = set(registry.all_surface_ids())
    bogus = refs - registered
    assert not bogus, (
        f"Inventory references checks that are not registered: {sorted(bogus)}"
    )


def test_every_registered_check_is_referenced_in_inventory() -> None:
    refs = _referenced_check_ids()
    registered = set(registry.all_surface_ids())
    missing = registered - refs
    assert not missing, (
        f"Checks registered in code but not declared in inventory: {sorted(missing)}"
    )
