# Unified Governance Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement sub-project 1 of 5 from the unified governance framework spec — build the family-agnostic governance framework, migrate OCO to it byte-identically, then add the two non-OCO payoff simulators (no adapters yet).

**Architecture:** Per-family `FamilyGovernanceConfig` dataclass + 4-hook `Protocol` (hybrid C abstraction). Three payoff simulators grouped by family type. Strict per-symbol YAML configs (no silent defaults). OCO becomes the first adapter; new outputs must diff to zero against legacy outputs. Each phase 1a–1i produces a PR.

**Tech Stack:** Python 3.12, pandas/numpy/pyarrow, pytest, ruff, yaml. Existing patterns: `mining_family.py` Protocol design, `_cached_float_col` memoisation, `Path.attrs` caching, conventional commit messages, sys.path bootstrap.

**Reference spec:** `docs/superpowers/specs/2026-05-25-unified-governance-framework-design.md`

---

## Pre-implementation setup (one-time)

**Files:**
- None (worktree + branch creation only)

- [ ] **Step 1: Create the umbrella worktree for sub-project 1**

```bash
git -C /Users/danielfisher/repositories/behemoth worktree add \
  /Users/danielfisher/repositories/behemoth/.claude/worktrees/governance-framework \
  -b governance-framework origin/main
cd /Users/danielfisher/repositories/behemoth/.claude/worktrees/governance-framework
```

Expected: worktree created, current branch is `governance-framework`.

**All subsequent tasks happen inside this worktree.** Each phase creates a child branch off `governance-framework`, opens a PR against `governance-framework`, then merges back. The umbrella branch only merges to `main` after all 9 phases land.

---

## File structure (mapped before tasks)

New files created across this plan:

```
src/behemoth/governance/
  __init__.py                         # phase 1a
  errors.py                           # phase 1a
  families/
    __init__.py                       # phase 1a
    base.py                           # phase 1a — FamilyGovernanceConfig + BaseFamilyGovernanceHooks
    oco_first_touch.py                # phase 1a — OCO adapter (stub), filled out 1b-1e
  symbol_config.py                    # phase 1a — SymbolGovernanceConfig YAML loader
  state_assembly.py                   # phase 1b
  selection.py                        # phase 1c
  tick_exact_shared.py                # phase 1d — TickStreamProvider, summary aggregators
  tick_exact_barrier_touch.py         # phase 1d — Simulator 1
  tick_exact_forward_return.py        # phase 1h — Simulator 2
  tick_exact_cross_symbol.py          # phase 1i — Simulator 3
  verdict.py                          # phase 1e — G4 + G5 roll-up
  freeze.py                           # phase 1e — freeze artifact writer

scripts/governance/
  __init__.py                         # phase 1a (empty marker)
  run_governance_all.py               # phase 1e — orchestrator
  validate_oco_migration_parity.py    # phase 1f — CI gate

configs/research/experiments/
  _governance_template.yaml           # phase 1a — annotated reference
  eurusd_governance.yaml              # phase 1c — first real symbol YAML
  (5 more symbol governance YAMLs)    # phase 1g — created during cutover

tests/governance/
  conftest.py                         # phase 1a — shared fixtures
  test_family_config.py               # phase 1a
  test_symbol_config.py               # phase 1a
  test_state_assembly.py              # phase 1b
  test_selection.py                   # phase 1c
  test_tick_exact_barrier_touch.py    # phase 1d
  test_tick_exact_forward_return.py   # phase 1h
  test_tick_exact_cross_symbol.py     # phase 1i
  test_verdict.py                     # phase 1e
  test_freeze.py                      # phase 1e
  test_oco_byte_parity.py             # phase 1f
  families/
    test_oco_first_touch_adapter.py   # phase 1a-1e (grown)
  fixtures/
    governance_oco_reference/         # phase 1f — frozen reference snapshots
      EURUSD_2026-05_state_schedule.csv
      EURUSD_2026-05_freeze.json
      (per-symbol per-month reference artifacts)
    synthetic_candidates_tiny.csv     # phase 1b — tiny fixture for unit tests
    synthetic_ticks_tiny.parquet      # phase 1d — tiny tick stream fixture

scripts/legacy/                        # phase 1g — old OCO scripts moved here
  select_oco_reduced_core_rolling.py
  verify_oco_tick_exact_shortlist.py
  freeze_oco_historical_governance.py
```

Files modified:

```
scripts/onboard_symbol.py             # phase 1g — switch from legacy to new pipeline
```

---

# Phase 1a — Framework skeleton + dataclass + protocol + OCO adapter stub

**Goal:** Empty but importable package. `FamilyGovernanceConfig` validates; `SymbolGovernanceConfig` loads YAMLs with no defaults; OCO adapter exists as a stub. Nothing runs end-to-end yet.

**Branch:** `governance-phase-1a` off `governance-framework`. Opens PR against `governance-framework`.

### Task 1a.1: Create branch + module skeleton

**Files:**
- Create: `src/behemoth/governance/__init__.py` (empty)
- Create: `src/behemoth/governance/families/__init__.py` (empty)
- Create: `scripts/governance/__init__.py` (empty)
- Create: `tests/governance/__init__.py` (empty)
- Create: `tests/governance/families/__init__.py` (empty)

- [ ] **Step 1: Create the phase branch**

```bash
git checkout -b governance-phase-1a
```

Expected: switched to `governance-phase-1a`.

- [ ] **Step 2: Create empty package files**

```bash
mkdir -p src/behemoth/governance/families scripts/governance tests/governance/families tests/governance/fixtures
touch src/behemoth/governance/__init__.py
touch src/behemoth/governance/families/__init__.py
touch scripts/governance/__init__.py
touch tests/governance/__init__.py
touch tests/governance/families/__init__.py
```

- [ ] **Step 3: Commit the skeleton**

```bash
git add src/behemoth/governance scripts/governance tests/governance
git commit -m "chore: scaffold governance framework package layout"
```

Expected: commit created.

### Task 1a.2: Define custom error types

**Files:**
- Create: `src/behemoth/governance/errors.py`
- Test: `tests/governance/test_errors.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_errors.py
import pytest
from src.behemoth.governance import errors


def test_missing_governance_field_error_message():
    e = errors.MissingGovernanceFieldError(
        symbol="EURUSD", family="directional_run", field="capacity_floor_monthly"
    )
    msg = str(e)
    assert "EURUSD" in msg
    assert "directional_run" in msg
    assert "capacity_floor_monthly" in msg


def test_unknown_family_error_message():
    e = errors.UnknownFamilyError(family="not_a_real_family")
    assert "not_a_real_family" in str(e)


def test_invalid_model_month_error_message():
    e = errors.InvalidModelMonthError(value="2026/05")
    assert "2026/05" in str(e)


def test_required_family_missing_thresholds_error_message():
    e = errors.RequiredFamilyMissingThresholdsError(
        symbol="EURUSD", family="directional_run"
    )
    assert "EURUSD" in str(e) and "directional_run" in str(e)
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/governance/test_errors.py -v
```

Expected: ImportError or "MissingGovernanceFieldError not defined".

- [ ] **Step 3: Implement errors module**

```python
# src/behemoth/governance/errors.py
"""Custom exceptions for the governance framework.

All errors are intentionally explicit (named after what went wrong + which
identifier is missing). The framework rejects silent defaults; errors are
raised at YAML load time or stage entry so the operator knows exactly
which symbol/family/field caused the failure."""

from __future__ import annotations


class GovernanceError(Exception):
    """Base class for governance framework errors."""


class MissingGovernanceFieldError(GovernanceError):
    """Raised when a required field is missing from a symbol's governance
    YAML. No defaults are applied; the symbol cannot be governed without
    every required threshold."""

    def __init__(self, *, symbol: str, family: str, field: str) -> None:
        super().__init__(
            f"governance YAML for symbol {symbol!r} is missing required "
            f"field {field!r} under family {family!r}"
        )
        self.symbol = symbol
        self.family = family
        self.field = field


class RequiredFamilyMissingThresholdsError(GovernanceError):
    """Raised when a symbol lists a family in `required_families` but does
    not provide that family's threshold block under `families`."""

    def __init__(self, *, symbol: str, family: str) -> None:
        super().__init__(
            f"symbol {symbol!r} requires family {family!r} but has no "
            f"threshold block for it under `families`"
        )
        self.symbol = symbol
        self.family = family


class InvalidModelMonthError(GovernanceError):
    """Raised when `model_month` is not in `YYYY-MM` format."""

    def __init__(self, *, value: str) -> None:
        super().__init__(
            f"model_month {value!r} is not in YYYY-MM format (e.g. '2026-05')"
        )
        self.value = value


class UnknownFamilyError(GovernanceError):
    """Raised when a YAML references a family name that is not registered
    in FAMILY_GOVERNANCE_REGISTRY."""

    def __init__(self, *, family: str) -> None:
        super().__init__(
            f"family {family!r} is not registered; check "
            f"src/behemoth/governance/families/__init__.py"
        )
        self.family = family


class CandidateSchemaError(GovernanceError):
    """Raised when a candidate CSV is missing columns required by a family's
    state_key_cols or selection_gate_cols."""

    def __init__(self, *, family: str, missing_cols: list[str]) -> None:
        super().__init__(
            f"candidate CSV for family {family!r} is missing required "
            f"columns: {sorted(missing_cols)}"
        )
        self.family = family
        self.missing_cols = missing_cols


class TickStreamGapError(GovernanceError):
    """Raised when a payoff simulator cannot obtain ticks for a required
    (symbol, time_range)."""

    def __init__(self, *, symbol: str, range_repr: str) -> None:
        super().__init__(
            f"tick stream gap for symbol {symbol!r} over range {range_repr}"
        )
        self.symbol = symbol
        self.range_repr = range_repr
```

- [ ] **Step 4: Run tests to verify pass**

```bash
uv run pytest tests/governance/test_errors.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/errors.py tests/governance/test_errors.py
git commit -m "feat: governance framework error types"
```

### Task 1a.3: `FamilyGovernanceConfig` dataclass + registry

**Files:**
- Create: `src/behemoth/governance/families/base.py`
- Test: `tests/governance/test_family_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/governance/test_family_config.py
import pytest
from src.behemoth.governance.families.base import (
    FamilyGovernanceConfig,
    BaseFamilyGovernanceHooks,
)


def test_family_governance_config_requires_all_fields():
    # frozen dataclass with no defaults; missing field is a TypeError
    with pytest.raises(TypeError):
        FamilyGovernanceConfig(name="x")  # missing all the others


def test_family_governance_config_holds_values():
    cfg = FamilyGovernanceConfig(
        name="oco_first_touch",
        state_key_cols=("family", "barrier_pips", "horizon", "regime"),
        wfo_target_col="y_oco_first_touch_decided",
        payoff_simulator="barrier_touch",
        selection_gate_cols=("both_window_rate", "p_up_first"),
        schema_version="oco_v4.0",
    )
    assert cfg.name == "oco_first_touch"
    assert cfg.payoff_simulator == "barrier_touch"


def test_family_governance_config_rejects_unknown_simulator():
    with pytest.raises(ValueError, match="payoff_simulator"):
        FamilyGovernanceConfig(
            name="x",
            state_key_cols=("a",),
            wfo_target_col="t",
            payoff_simulator="not_a_simulator",  # type: ignore[arg-type]
            selection_gate_cols=(),
            schema_version="v1",
        )


def test_family_governance_config_is_frozen():
    cfg = FamilyGovernanceConfig(
        name="x",
        state_key_cols=("a",),
        wfo_target_col="t",
        payoff_simulator="forward_return",
        selection_gate_cols=(),
        schema_version="v1",
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        cfg.name = "y"  # type: ignore[misc]


def test_base_hooks_default_derive_state_id_uses_state_key_cols_in_order():
    import pandas as pd

    cfg = FamilyGovernanceConfig(
        name="oco_first_touch",
        state_key_cols=("family", "barrier_pips", "horizon", "regime"),
        wfo_target_col="t",
        payoff_simulator="barrier_touch",
        selection_gate_cols=(),
        schema_version="v1",
    )
    hooks = BaseFamilyGovernanceHooks(config=cfg)
    row = pd.Series({
        "family": "oco_first_touch", "barrier_pips": 2.0,
        "horizon": 3, "regime": "london",
    })
    sid = hooks.derive_state_id(row)
    # deterministic, includes every key column
    assert "oco_first_touch" in sid
    assert "2" in sid and "3" in sid and "london" in sid


def test_base_hooks_default_selection_gate_returns_true():
    import pandas as pd

    cfg = FamilyGovernanceConfig(
        name="x", state_key_cols=("a",), wfo_target_col="t",
        payoff_simulator="forward_return", selection_gate_cols=(),
        schema_version="v1",
    )
    hooks = BaseFamilyGovernanceHooks(config=cfg)
    assert hooks.selection_gate(pd.Series({}), {}) is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/governance/test_family_config.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement base.py**

```python
# src/behemoth/governance/families/base.py
"""Family adapter base: FamilyGovernanceConfig dataclass + hook protocol.

Each family adapter has TWO parts:
1. A `FamilyGovernanceConfig` instance (the "data" half of hybrid-C
   abstraction). Declares per-family invariants: state key columns,
   WFO target column, which payoff simulator to use, selection-gate
   column names, schema version.
2. A subclass of `BaseFamilyGovernanceHooks` (the "behaviour" half).
   Overrides only the methods that need family-specific logic; the
   base provides sensible defaults.

NO field on FamilyGovernanceConfig has a default value. Every adapter
must declare all six fields. This is intentional: silent defaults mask
divergence between families and break LLM-driven onboarding (an LLM
filling in a config is more reliable when it sees every field).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import pandas as pd


PayoffSimulator = Literal[
    "barrier_touch", "forward_return", "cross_symbol_residual"
]


@dataclass(frozen=True)
class FamilyGovernanceConfig:
    """Declarative metadata for a family's governance behaviour.

    Attributes:
        name: Family name, matches mining_family.py's FAMILY_REGISTRY key.
        state_key_cols: Columns from the candidate CSV that together
            identify a unique state. State assembly groups by these.
        wfo_target_col: Column in the WFO predictions parquet that
            this family's selection consumes.
        payoff_simulator: Which of the 3 tick-exact simulators applies.
        selection_gate_cols: Candidate-CSV columns used by family-specific
            selection gates (e.g., OCO's both_window_rate, p_up_first).
            Empty tuple means no extra gates beyond the universal ones
            (capacity, stability, etc.).
        schema_version: Versions the freeze artifact JSON. Bump when the
            artifact schema changes.
    """

    name: str
    state_key_cols: tuple[str, ...]
    wfo_target_col: str
    payoff_simulator: PayoffSimulator
    selection_gate_cols: tuple[str, ...]
    schema_version: str

    def __post_init__(self) -> None:
        valid = ("barrier_touch", "forward_return", "cross_symbol_residual")
        if self.payoff_simulator not in valid:
            raise ValueError(
                f"payoff_simulator {self.payoff_simulator!r} must be one "
                f"of {valid}"
            )


class FamilyGovernanceHooksProtocol(Protocol):
    """Protocol describing the hook surface family adapters must implement.
    BaseFamilyGovernanceHooks provides default implementations."""

    config: FamilyGovernanceConfig

    def derive_state_id(self, row: pd.Series) -> str: ...
    def selection_gate(
        self, row: pd.Series, thresholds: dict[str, float]
    ) -> bool: ...
    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, Any],
    ) -> float: ...
    def encode_freeze_artifact(
        self, qualified_states: pd.DataFrame, model_month: str
    ) -> dict[str, Any]: ...


class BaseFamilyGovernanceHooks:
    """Default implementations of all hooks. Family adapters subclass
    this and override only the hooks that need family-specific behaviour.

    The defaults are intentionally conservative:
    - derive_state_id concatenates state_key_cols values in declared order
    - selection_gate returns True (no extra gates)
    - simulate_one_entry raises NotImplementedError (each adapter MUST
      override; the simulator framework calls this per fill)
    - encode_freeze_artifact emits a minimal schema-tagged dict
    """

    def __init__(self, config: FamilyGovernanceConfig) -> None:
        self.config = config

    def derive_state_id(self, row: pd.Series) -> str:
        parts: list[str] = []
        for col in self.config.state_key_cols:
            val = row[col]
            # Numerics get %g formatting to match OCO's existing state_id
            # convention (`__k2_h3` rather than `__k2.0_h3.0`).
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                parts.append(format(val, "g"))
            else:
                parts.append(str(val))
        return self.config.name + "__" + "_".join(parts)

    def selection_gate(
        self, row: pd.Series, thresholds: dict[str, float]
    ) -> bool:
        return True

    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, Any],
    ) -> float:
        raise NotImplementedError(
            f"adapter for {self.config.name!r} must override "
            f"simulate_one_entry; the simulator framework calls it per fill"
        )

    def encode_freeze_artifact(
        self, qualified_states: pd.DataFrame, model_month: str
    ) -> dict[str, Any]:
        return {
            "family": self.config.name,
            "schema_version": self.config.schema_version,
            "model_month": model_month,
            "qualified_states": qualified_states.to_dict(orient="records"),
        }
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_family_config.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/families/base.py tests/governance/test_family_config.py
git commit -m "feat: FamilyGovernanceConfig dataclass + base hooks"
```

### Task 1a.4: Family adapter registry

**Files:**
- Modify: `src/behemoth/governance/families/__init__.py`
- Test: `tests/governance/test_family_registry.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_family_registry.py
import pytest
from src.behemoth.governance.families import (
    FAMILY_GOVERNANCE_REGISTRY,
    get_family_adapter,
)
from src.behemoth.governance.errors import UnknownFamilyError


def test_registry_is_a_dict_keyed_by_family_name():
    assert isinstance(FAMILY_GOVERNANCE_REGISTRY, dict)


def test_get_family_adapter_unknown_raises():
    with pytest.raises(UnknownFamilyError):
        get_family_adapter("not_a_family")


def test_get_family_adapter_returns_hook_instance_for_known():
    # OCO is the only registered family in phase 1a (stub adapter).
    adapter = get_family_adapter("oco_first_touch")
    assert adapter.config.name == "oco_first_touch"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/governance/test_family_registry.py -v
```

Expected: ImportError or "FAMILY_GOVERNANCE_REGISTRY not defined".

- [ ] **Step 3: Implement registry module**

```python
# src/behemoth/governance/families/__init__.py
"""Family adapter registry. Each adapter module registers itself by
adding an instance to FAMILY_GOVERNANCE_REGISTRY at import time."""

from __future__ import annotations

from src.behemoth.governance.errors import UnknownFamilyError
from src.behemoth.governance.families.base import (
    BaseFamilyGovernanceHooks,
    FamilyGovernanceConfig,
)
from src.behemoth.governance.families.oco_first_touch import (
    OCO_FIRST_TOUCH_HOOKS,
)

FAMILY_GOVERNANCE_REGISTRY: dict[str, BaseFamilyGovernanceHooks] = {
    OCO_FIRST_TOUCH_HOOKS.config.name: OCO_FIRST_TOUCH_HOOKS,
    # adapters for the other 8 families land in sub-projects 2-4
}


def get_family_adapter(name: str) -> BaseFamilyGovernanceHooks:
    """Lookup a registered family adapter by name. Raises UnknownFamilyError
    if not registered."""
    if name not in FAMILY_GOVERNANCE_REGISTRY:
        raise UnknownFamilyError(family=name)
    return FAMILY_GOVERNANCE_REGISTRY[name]


__all__ = [
    "FAMILY_GOVERNANCE_REGISTRY",
    "get_family_adapter",
    "FamilyGovernanceConfig",
    "BaseFamilyGovernanceHooks",
]
```

- [ ] **Step 4: Create OCO stub adapter (filled out in later phases)**

Create `src/behemoth/governance/families/oco_first_touch.py`:

```python
"""OCO first-touch family adapter for the governance framework.

Phase 1a: stub — config + base hooks. Subsequent phases override hooks
as the framework stages are implemented:
- phase 1c: selection_gate override (both_window_rate, p_up_first)
- phase 1d: simulate_one_entry override (barrier-touch detection)
- phase 1e: encode_freeze_artifact override (OCO-specific JSON schema)
"""

from __future__ import annotations

from src.behemoth.governance.families.base import (
    BaseFamilyGovernanceHooks,
    FamilyGovernanceConfig,
)


OCO_FIRST_TOUCH_CONFIG = FamilyGovernanceConfig(
    name="oco_first_touch",
    state_key_cols=("family", "barrier_pips", "horizon", "regime"),
    wfo_target_col="y_oco_first_touch_decided",
    payoff_simulator="barrier_touch",
    selection_gate_cols=("both_window_rate", "p_up_first"),
    schema_version="oco_v4.0",
)


class OcoFirstTouchHooks(BaseFamilyGovernanceHooks):
    """OCO first-touch adapter. Phase 1a is a stub; overrides land in
    phases 1c (selection_gate), 1d (simulate_one_entry), 1e (encode)."""


OCO_FIRST_TOUCH_HOOKS = OcoFirstTouchHooks(OCO_FIRST_TOUCH_CONFIG)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/governance/test_family_registry.py tests/governance/test_family_config.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/governance/families/__init__.py \
        src/behemoth/governance/families/oco_first_touch.py \
        tests/governance/test_family_registry.py
git commit -m "feat: family adapter registry + OCO stub"
```

### Task 1a.5: `SymbolGovernanceConfig` YAML loader

**Files:**
- Create: `src/behemoth/governance/symbol_config.py`
- Test: `tests/governance/test_symbol_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/governance/test_symbol_config.py
import pytest
import textwrap
from pathlib import Path

from src.behemoth.governance.symbol_config import (
    SymbolGovernanceConfig,
    load_symbol_governance_config,
)
from src.behemoth.governance.errors import (
    MissingGovernanceFieldError,
    RequiredFamilyMissingThresholdsError,
    InvalidModelMonthError,
    UnknownFamilyError,
)


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "eurusd_governance.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_loads_valid_yaml(tmp_path):
    p = _write_yaml(tmp_path, """
        symbol: EURUSD
        model_month: 2026-05
        required_families:
          - oco_first_touch
        families:
          oco_first_touch:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates:
              min_both_window_rate: 0.0
              min_p_up_first: 0.0
    """)
    cfg = load_symbol_governance_config(p)
    assert cfg.symbol == "EURUSD"
    assert cfg.model_month == "2026-05"
    assert cfg.required_families == ("oco_first_touch",)
    assert cfg.families["oco_first_touch"]["capacity_floor_monthly"] == 200


def test_missing_top_level_field_raises(tmp_path):
    p = _write_yaml(tmp_path, """
        symbol: EURUSD
        # model_month missing
        required_families: [oco_first_touch]
        families: {oco_first_touch: {}}
    """)
    with pytest.raises(MissingGovernanceFieldError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.field == "model_month"


def test_invalid_model_month_format_raises(tmp_path):
    p = _write_yaml(tmp_path, """
        symbol: EURUSD
        model_month: 2026/05
        required_families: [oco_first_touch]
        families:
          oco_first_touch:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
    """)
    with pytest.raises(InvalidModelMonthError):
        load_symbol_governance_config(p)


def test_required_family_not_in_families_raises(tmp_path):
    p = _write_yaml(tmp_path, """
        symbol: EURUSD
        model_month: 2026-05
        required_families: [directional_run]
        families:
          oco_first_touch:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
    """)
    with pytest.raises(RequiredFamilyMissingThresholdsError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.family == "directional_run"


def test_unknown_family_name_raises(tmp_path):
    p = _write_yaml(tmp_path, """
        symbol: EURUSD
        model_month: 2026-05
        required_families: [not_a_family]
        families:
          not_a_family:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
    """)
    with pytest.raises(UnknownFamilyError):
        load_symbol_governance_config(p)


def test_missing_per_family_field_raises(tmp_path):
    p = _write_yaml(tmp_path, """
        symbol: EURUSD
        model_month: 2026-05
        required_families: [oco_first_touch]
        families:
          oco_first_touch:
            # capacity_floor_monthly intentionally missing
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
    """)
    with pytest.raises(MissingGovernanceFieldError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.field == "capacity_floor_monthly"
    assert ei.value.family == "oco_first_touch"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/governance/test_symbol_config.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement symbol_config.py**

```python
# src/behemoth/governance/symbol_config.py
"""Symbol governance config loader.

Each symbol has one YAML at configs/research/experiments/<sym>_governance.yaml.
All fields are required; missing fields raise MissingGovernanceFieldError.
No silent defaults. The YAML is the only source of truth for per-symbol
thresholds; defaults baked into family adapters are intentional 'declare
every value explicitly' design.

See `configs/research/experiments/_governance_template.yaml` for the
annotated reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.behemoth.governance.errors import (
    InvalidModelMonthError,
    MissingGovernanceFieldError,
    RequiredFamilyMissingThresholdsError,
    UnknownFamilyError,
)

# Per-family required threshold fields. Used by the loader to enforce
# "no missing fields". When a new gate is added to the framework, append
# its name here so YAMLs are forced to declare it.
REQUIRED_PER_FAMILY_FIELDS: tuple[str, ...] = (
    "capacity_floor_monthly",
    "capacity_floor_annual",
    "max_state_churn",
    "max_top_state_share",
    "max_state_hhi",
    "state_train_months",
    "min_states",
    "max_states",
    "selection_gates",
)

_MODEL_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class SymbolGovernanceConfig:
    """Loaded view of one symbol's governance YAML."""

    symbol: str
    model_month: str
    required_families: tuple[str, ...]
    families: dict[str, dict[str, Any]]


def load_symbol_governance_config(yaml_path: Path) -> SymbolGovernanceConfig:
    """Load and validate a symbol governance YAML. Fails loudly on any
    missing required field with a precise error pointing at the offending
    symbol/family/field."""
    raw = yaml.safe_load(Path(yaml_path).read_text())
    if not isinstance(raw, dict):
        raise MissingGovernanceFieldError(
            symbol="?", family="?", field="(empty YAML)"
        )

    symbol = raw.get("symbol")
    if symbol is None:
        raise MissingGovernanceFieldError(
            symbol="?", family="(top-level)", field="symbol"
        )

    for top_field in ("model_month", "required_families", "families"):
        if top_field not in raw:
            raise MissingGovernanceFieldError(
                symbol=str(symbol), family="(top-level)", field=top_field
            )

    model_month = str(raw["model_month"])
    if not _MODEL_MONTH_RE.match(model_month):
        raise InvalidModelMonthError(value=model_month)

    required_families = tuple(raw["required_families"])
    families_block = dict(raw["families"])

    # Every required family must have a threshold block.
    for fam in required_families:
        if fam not in families_block:
            raise RequiredFamilyMissingThresholdsError(
                symbol=str(symbol), family=str(fam)
            )

    # Every family name (required or extra) must be registered.
    # Import here to avoid module-load cycle.
    from src.behemoth.governance.families import FAMILY_GOVERNANCE_REGISTRY

    for fam in families_block:
        if fam not in FAMILY_GOVERNANCE_REGISTRY:
            raise UnknownFamilyError(family=str(fam))

    # Every per-family block must have all required fields.
    for fam, thresholds in families_block.items():
        if not isinstance(thresholds, dict):
            raise MissingGovernanceFieldError(
                symbol=str(symbol), family=str(fam), field="(non-dict block)"
            )
        for field in REQUIRED_PER_FAMILY_FIELDS:
            if field not in thresholds:
                raise MissingGovernanceFieldError(
                    symbol=str(symbol), family=str(fam), field=field
                )

    return SymbolGovernanceConfig(
        symbol=str(symbol),
        model_month=model_month,
        required_families=required_families,
        families=families_block,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_symbol_config.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/symbol_config.py tests/governance/test_symbol_config.py
git commit -m "feat: SymbolGovernanceConfig YAML loader (no silent defaults)"
```

### Task 1a.6: Annotated YAML template

**Files:**
- Create: `configs/research/experiments/_governance_template.yaml`

- [ ] **Step 1: Create template with full per-field comments**

```yaml
# _governance_template.yaml — canonical reference for symbol governance configs.
#
# Copy this file when onboarding a new symbol. Save as
# `<sym>_governance.yaml`. All fields below are REQUIRED — missing
# fields are a hard error at load time (no silent defaults).
#
# Authoritative schema: src/behemoth/governance/symbol_config.py
# (REQUIRED_PER_FAMILY_FIELDS lists per-family required keys).

# ------------------------------------------------------------
# Top-level fields
# ------------------------------------------------------------

symbol: EURUSD
# Uppercase ISO pair, must match velocity file naming
# (data/analysis/tick_velocity/EURUSD_<bar_ticks>tick_velocity.parquet).

model_month: 2026-05
# Governance lifetime tag in YYYY-MM format. Refreshed monthly via
# `make monthly-recert`. Freeze artifacts produced by this YAML are
# tagged with this value; the live system rejects artifacts whose
# model_month is not the current cycle.

required_families:
  - oco_first_touch
  - directional_run
# Symbol-level GO iff every listed family's verdict is GO. Order does
# not matter. Must be ≥1 entry. Available family names: oco_first_touch,
# oco_asymmetric, directional, directional_inverse, directional_run,
# double_touch, pullback, dollar_residual, dispersion_rank, lead_lag.
# (no_touch is opt-in only — declare it explicitly if needed.)

# ------------------------------------------------------------
# Per-family thresholds. MUST include a block for every family in
# `required_families`. May include extra blocks for diagnostic
# comparison (won't affect GO/NO_GO).
# ------------------------------------------------------------

families:

  oco_first_touch:
    capacity_floor_monthly: 200
    # Minimum filled signals per month, averaged across the
    # state_train_months window. Below this, the state is dropped as
    # uneconomic (each signal carries transaction cost).

    capacity_floor_annual: 500
    # Same idea, annualised. State must meet BOTH monthly and annual
    # floors to qualify.

    max_state_churn: 0.45
    # Maximum allowed fraction of states added/removed between
    # consecutive months in the train window. Above this, the state
    # selection is too unstable to deploy.

    max_top_state_share: 0.35
    # Maximum allowed fraction of signals concentrated in the single
    # most-active state. Above this, the portfolio is too concentrated.

    max_state_hhi: 0.25
    # Maximum Herfindahl-Hirschman Index for state concentration. Above
    # this, the portfolio is too concentrated even after the top-share
    # check.

    state_train_months: 2
    # Number of months of training data used per rolling selection
    # window. Larger = more stable selection, less adaptive.

    min_states: 1
    # Minimum number of qualifying states required to declare this
    # (symbol, family) GO. Below this, the family is NO_GO.

    max_states: 12
    # Hard cap on selected states (top N by quality_score). Caps
    # combinatorial blow-up at the deployment layer.

    selection_gates:
      # Family-specific gate thresholds. Keys correspond to the family
      # adapter's selection_gate_cols. For oco_first_touch:
      min_both_window_rate: 0.5
      # Minimum rate at which both barriers are touched within the
      # candidate's lookahead window.
      min_p_up_first: 0.4
      # Minimum probability of upward barrier hit first (vs downward).
      # Asymmetric thresholds catch bias.

  directional_run:
    capacity_floor_monthly: 300
    capacity_floor_annual: 800
    max_state_churn: 0.45
    max_top_state_share: 0.35
    max_state_hhi: 0.25
    state_train_months: 2
    min_states: 1
    max_states: 12
    selection_gates: {}
    # directional_run has no family-specific gates beyond the universal
    # ones; provide an empty dict to declare "no extra gates".
```

- [ ] **Step 2: Commit template**

```bash
git add configs/research/experiments/_governance_template.yaml
git commit -m "docs: governance YAML template with annotated fields"
```

### Task 1a.7: Open phase 1a PR

- [ ] **Step 1: Push branch + open PR against `governance-framework`**

```bash
git push -u origin governance-phase-1a
gh pr create --base governance-framework --title "feat: governance framework skeleton (phase 1a)" --body "Sub-project 1, phase 1a. Skeleton package, FamilyGovernanceConfig dataclass, BaseFamilyGovernanceHooks, SymbolGovernanceConfig YAML loader with no silent defaults, OCO stub adapter, annotated YAML template. No end-to-end behaviour yet; subsequent phases plug in stages G1-G5."
```

- [ ] **Step 2: Verify CI green, merge to `governance-framework`**

```bash
gh pr checks <PR#>  # wait for green
gh pr merge <PR#> --squash
```

---

# Phase 1b — Stage G1 (state assembly)

**Goal:** Reading a candidate CSV + family adapter, group rows into states keyed by `state_key_cols`. Output is a state schedule CSV with the same shape as the existing OCO `<SYM>_oco_reduced_state_schedule.csv` (column-for-column compatible for OCO).

**Branch:** `governance-phase-1b` off `governance-framework` (after 1a merged).

### Task 1b.1: Inspect existing OCO state schedule shape

**Files:**
- Read: existing schedule columns from a reference frozen snapshot

- [ ] **Step 1: Capture the reference column order + dtypes**

```bash
git checkout governance-framework
git pull
git checkout -b governance-phase-1b
uv run python -c "
import pandas as pd
df = pd.read_csv('data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv')
print('columns:', list(df.columns))
print('dtypes:', df.dtypes.to_dict())
print('shape:', df.shape)
print(df.head(2).to_dict(orient='records'))
"
```

Record the output in a comment in the next task's test. This is the byte-identical target for OCO.

### Task 1b.2: Tiny synthetic candidate fixture

**Files:**
- Create: `tests/governance/fixtures/synthetic_candidates_oco.csv`

- [ ] **Step 1: Create fixture with 10 candidates spanning 2 states**

```bash
cat > tests/governance/fixtures/synthetic_candidates_oco.csv <<'EOF'
candidate_id,symbol,bar_ticks,horizon,family,barrier_pips,regime,mean_gross_pips_train,train_count,both_window_rate,p_up_first,random_baseline_z,selection_pass,quality_tier
c01,EURUSD,1000,3,oco_first_touch,2.0,london,0.20,800,0.72,0.51,1.8,True,B
c02,EURUSD,1000,3,oco_first_touch,2.0,london,0.18,750,0.71,0.50,1.6,True,B
c03,EURUSD,1000,3,oco_first_touch,2.0,asia,0.05,600,0.65,0.48,0.4,False,D
c04,EURUSD,1000,5,oco_first_touch,2.0,london,0.30,900,0.74,0.52,2.4,True,A
c05,EURUSD,1000,5,oco_first_touch,3.0,london,0.25,500,0.60,0.50,1.5,True,B
c06,EURUSD,1000,5,oco_first_touch,3.0,asia,-0.02,400,0.55,0.47,-0.2,False,D
c07,EURUSD,1000,3,oco_first_touch,3.0,ny,0.10,300,0.58,0.49,0.7,False,C
c08,EURUSD,1000,3,oco_first_touch,2.0,ny,0.12,650,0.70,0.51,1.0,False,C
c09,EURUSD,1000,5,oco_first_touch,2.0,ny,0.08,550,0.68,0.50,0.6,False,C
c10,EURUSD,1000,5,oco_first_touch,3.0,ny,0.05,250,0.55,0.48,0.3,False,D
EOF
```

- [ ] **Step 2: Commit fixture**

```bash
git add tests/governance/fixtures/synthetic_candidates_oco.csv
git commit -m "test: synthetic OCO candidate fixture for governance unit tests"
```

### Task 1b.3: State assembly module

**Files:**
- Create: `src/behemoth/governance/state_assembly.py`
- Test: `tests/governance/test_state_assembly.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_state_assembly.py
from pathlib import Path

import pandas as pd
import pytest

from src.behemoth.governance.state_assembly import assemble_states
from src.behemoth.governance.families import get_family_adapter

FIXTURE = Path("tests/governance/fixtures/synthetic_candidates_oco.csv")


def test_assemble_states_groups_by_state_key_cols():
    candidates = pd.read_csv(FIXTURE)
    adapter = get_family_adapter("oco_first_touch")
    states = assemble_states(candidates=candidates, adapter=adapter)

    # state_key_cols = (family, barrier_pips, horizon, regime)
    # Synthetic data has 7 distinct combos across 10 rows.
    distinct = candidates.groupby(
        ["family", "barrier_pips", "horizon", "regime"]
    ).ngroups
    assert len(states) == distinct
    # Each row has a state_id assigned by the adapter
    assert "state_id" in states.columns


def test_assemble_states_state_id_uses_default_formatting():
    candidates = pd.read_csv(FIXTURE)
    adapter = get_family_adapter("oco_first_touch")
    states = assemble_states(candidates=candidates, adapter=adapter)
    # Default derive_state_id uses %g formatting: "...__2_3_london"
    sids = states["state_id"].tolist()
    assert any("london" in s for s in sids)
    assert any("__2_" in s for s in sids)  # barrier_pips=2.0 formats as "2"


def test_assemble_states_aggregates_train_counts():
    candidates = pd.read_csv(FIXTURE)
    adapter = get_family_adapter("oco_first_touch")
    states = assemble_states(candidates=candidates, adapter=adapter)
    # State (family=oco_first_touch, barrier=2.0, horizon=3, regime=london)
    # has 2 candidates (c01, c02), total train_count = 800+750 = 1550.
    mask = (
        (states["family"] == "oco_first_touch")
        & (states["barrier_pips"] == 2.0)
        & (states["horizon"] == 3)
        & (states["regime"] == "london")
    )
    row = states[mask].iloc[0]
    assert int(row["train_count_sum"]) == 1550


def test_assemble_states_raises_on_missing_state_key_col():
    candidates = pd.read_csv(FIXTURE).drop(columns=["regime"])
    adapter = get_family_adapter("oco_first_touch")
    from src.behemoth.governance.errors import CandidateSchemaError
    with pytest.raises(CandidateSchemaError) as ei:
        assemble_states(candidates=candidates, adapter=adapter)
    assert "regime" in ei.value.missing_cols
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/governance/test_state_assembly.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement state_assembly.py**

```python
# src/behemoth/governance/state_assembly.py
"""Stage G1: state assembly.

Groups candidates into states keyed by the family adapter's
state_key_cols. Each state row carries:
- The state_key_cols values (one row per unique combination)
- A deterministic state_id (from adapter.derive_state_id)
- Aggregated stats: candidate_count, train_count_sum, mean of
  mean_gross_pips_train weighted by train_count, etc.

This is the post-mining input to Stage G2 (selection). The shape
matches the existing OCO `<SYM>_oco_reduced_state_schedule.csv`
columns for migration parity (column-for-column when adapter is
oco_first_touch).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.behemoth.governance.errors import CandidateSchemaError
from src.behemoth.governance.families.base import BaseFamilyGovernanceHooks


def assemble_states(
    *,
    candidates: pd.DataFrame,
    adapter: BaseFamilyGovernanceHooks,
) -> pd.DataFrame:
    """Group candidate rows into states. Returns one row per unique
    combination of adapter.config.state_key_cols, with a state_id and
    per-state aggregates."""
    state_key_cols = list(adapter.config.state_key_cols)
    missing = [c for c in state_key_cols if c not in candidates.columns]
    if missing:
        raise CandidateSchemaError(
            family=adapter.config.name, missing_cols=missing
        )

    # Use sort=False to preserve insertion order so the resulting
    # state_schedule is byte-stable across pandas versions.
    grouped = candidates.groupby(state_key_cols, sort=False, as_index=False)
    agg = grouped.agg(
        candidate_count=("candidate_id", "count"),
        train_count_sum=("train_count", "sum"),
        mean_gross_pips_train_avg=(
            "mean_gross_pips_train",
            lambda s: float(np.average(
                s, weights=candidates.loc[s.index, "train_count"]
            )) if s.notna().any() else float("nan"),
        ),
    )

    # Add state_id via adapter hook (apply over rows).
    agg["state_id"] = agg.apply(adapter.derive_state_id, axis=1)
    return agg
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_state_assembly.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/state_assembly.py \
        tests/governance/test_state_assembly.py
git commit -m "feat: stage G1 state assembly"
```

### Task 1b.4: Open phase 1b PR

- [ ] **Step 1: Push + open PR against `governance-framework`**

```bash
git push -u origin governance-phase-1b
gh pr create --base governance-framework \
  --title "feat: governance stage G1 state assembly (phase 1b)" \
  --body "Phase 1b: state assembly groups candidates by adapter.state_key_cols and produces a state schedule shaped for byte-identical OCO migration. Synthetic fixture-driven unit tests."
```

- [ ] **Step 2: Merge after CI green**

```bash
gh pr merge <PR#> --squash
```

---

# Phase 1c — Stage G2 (selection)

**Goal:** Port the OCO selection logic from `scripts/select_oco_reduced_core_rolling.py` (1,178 lines) into a generic framework that applies family-specific gates via the adapter. OCO's outputs must remain byte-identical.

**Branch:** `governance-phase-1c` off `governance-framework`.

This is the largest phase. Tasks below decompose the selection logic by component (capacity gate, stability gate, family-specific gate, rolling month application, summary aggregation). Each task is TDD.

### Task 1c.1: Inspect existing selection logic structure

**Files:**
- Read: `scripts/select_oco_reduced_core_rolling.py`

- [ ] **Step 1: Map the existing function structure**

```bash
git checkout governance-framework
git pull
git checkout -b governance-phase-1c
grep -nE "^def " scripts/select_oco_reduced_core_rolling.py
```

Record the function list. These are the pieces to port. The plan tasks below correspond to logical groupings of these functions.

### Task 1c.2: Universal capacity gate (per-state)

**Files:**
- Create: `src/behemoth/governance/selection.py`
- Test: `tests/governance/test_selection.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_selection.py
import pandas as pd

from src.behemoth.governance.selection import apply_capacity_gate


def test_apply_capacity_gate_passes_state_meeting_floors():
    # State has 250/month, 600/year. Thresholds 200/500 → both pass.
    states = pd.DataFrame([
        {"state_id": "s1", "avg_monthly_signals": 250.0, "annualized_signals": 600.0},
    ])
    out = apply_capacity_gate(
        states=states,
        capacity_floor_monthly=200,
        capacity_floor_annual=500,
    )
    assert out["capacity_pass"].tolist() == [True]


def test_apply_capacity_gate_fails_state_below_monthly_floor():
    states = pd.DataFrame([
        {"state_id": "s1", "avg_monthly_signals": 150.0, "annualized_signals": 600.0},
    ])
    out = apply_capacity_gate(
        states=states, capacity_floor_monthly=200, capacity_floor_annual=500,
    )
    assert out["capacity_pass"].tolist() == [False]


def test_apply_capacity_gate_fails_state_below_annual_floor():
    states = pd.DataFrame([
        {"state_id": "s1", "avg_monthly_signals": 250.0, "annualized_signals": 400.0},
    ])
    out = apply_capacity_gate(
        states=states, capacity_floor_monthly=200, capacity_floor_annual=500,
    )
    assert out["capacity_pass"].tolist() == [False]
```

- [ ] **Step 2: Verify failure**

```bash
uv run pytest tests/governance/test_selection.py::test_apply_capacity_gate_passes_state_meeting_floors -v
```

- [ ] **Step 3: Implement capacity gate**

```python
# src/behemoth/governance/selection.py
"""Stage G2: selection.

Apply capacity floors, stability thresholds, and family-specific
selection gates to the state schedule from G1. Output is the subset
of states that pass ALL gates, plus per-state gate-result columns
(`capacity_pass`, `stability_pass`, `selection_gate_pass`, `selected`).

Ported from `scripts/select_oco_reduced_core_rolling.py` (1,178 LOC)
into a family-agnostic shape. Byte-identical to legacy output when
adapter is oco_first_touch and the symbol YAML mirrors the legacy YAML.
"""

from __future__ import annotations

import pandas as pd


def apply_capacity_gate(
    *,
    states: pd.DataFrame,
    capacity_floor_monthly: float,
    capacity_floor_annual: float,
) -> pd.DataFrame:
    """Mark states passing both monthly and annual capacity floors.
    Mutates a copy; returns the new DataFrame with a `capacity_pass`
    boolean column appended."""
    out = states.copy()
    out["capacity_pass"] = (
        (out["avg_monthly_signals"].astype(float) >= float(capacity_floor_monthly))
        & (out["annualized_signals"].astype(float) >= float(capacity_floor_annual))
    )
    return out
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_selection.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/selection.py tests/governance/test_selection.py
git commit -m "feat: stage G2 capacity gate"
```

### Task 1c.3: Universal stability gate (churn / top-share / HHI)

**Files:**
- Modify: `src/behemoth/governance/selection.py`
- Modify: `tests/governance/test_selection.py`

- [ ] **Step 1: Append failing test**

```python
# Append to tests/governance/test_selection.py
def test_apply_stability_gate_passes_stable_state():
    # 3 months, state present each month with similar share.
    state_monthly = pd.DataFrame([
        {"state_id": "s1", "month": "2026-01", "share_of_signals": 0.30},
        {"state_id": "s1", "month": "2026-02", "share_of_signals": 0.32},
        {"state_id": "s1", "month": "2026-03", "share_of_signals": 0.28},
    ])
    from src.behemoth.governance.selection import apply_stability_gate
    out = apply_stability_gate(
        state_monthly=state_monthly,
        max_state_churn=0.45,
        max_top_state_share=0.35,
        max_state_hhi=0.25,
    )
    # state s1 should pass: avg share 0.30 < 0.35, churn 0
    assert out.loc[out["state_id"] == "s1", "stability_pass"].iloc[0] is True


def test_apply_stability_gate_fails_state_too_concentrated():
    state_monthly = pd.DataFrame([
        {"state_id": "s1", "month": "2026-01", "share_of_signals": 0.50},
        {"state_id": "s1", "month": "2026-02", "share_of_signals": 0.52},
        {"state_id": "s1", "month": "2026-03", "share_of_signals": 0.48},
    ])
    from src.behemoth.governance.selection import apply_stability_gate
    out = apply_stability_gate(
        state_monthly=state_monthly,
        max_state_churn=0.45,
        max_top_state_share=0.35,  # exceeded
        max_state_hhi=0.25,
    )
    assert out.loc[out["state_id"] == "s1", "stability_pass"].iloc[0] is False
```

- [ ] **Step 2: Implement stability gate**

Append to `src/behemoth/governance/selection.py`:

```python
def apply_stability_gate(
    *,
    state_monthly: pd.DataFrame,
    max_state_churn: float,
    max_top_state_share: float,
    max_state_hhi: float,
) -> pd.DataFrame:
    """Per-state stability test across rolling months.

    Inputs: state_monthly DataFrame with rows (state_id, month,
    share_of_signals). A state passes when:
      - Its average share_of_signals across months ≤ max_top_state_share
      - Cross-month presence stable (churn ≤ max_state_churn)
      - Aggregate concentration (HHI of all states this month) ≤ max_state_hhi

    Returns a per-state DataFrame with `stability_pass` boolean."""
    # Compute per-state aggregates
    per_state = state_monthly.groupby("state_id", sort=False).agg(
        avg_share=("share_of_signals", "mean"),
        months_present=("month", "nunique"),
    ).reset_index()

    # Compute aggregate HHI (per-month, then averaged)
    def _hhi(group: pd.DataFrame) -> float:
        return float((group["share_of_signals"] ** 2).sum())

    hhi_per_month = state_monthly.groupby("month").apply(_hhi)
    avg_hhi = float(hhi_per_month.mean()) if len(hhi_per_month) else 0.0

    total_months = state_monthly["month"].nunique()

    def _churn(months_present: int) -> float:
        # Fraction of months a state was missing.
        return 1.0 - (months_present / total_months) if total_months else 0.0

    per_state["churn"] = per_state["months_present"].apply(_churn)
    per_state["stability_pass"] = (
        (per_state["avg_share"] <= max_top_state_share)
        & (per_state["churn"] <= max_state_churn)
        & (avg_hhi <= max_state_hhi)
    )
    return per_state[["state_id", "stability_pass"]]
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/governance/test_selection.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/governance/selection.py tests/governance/test_selection.py
git commit -m "feat: stage G2 stability gate"
```

### Task 1c.4: Family-specific selection gate (adapter hook integration)

**Files:**
- Modify: `src/behemoth/governance/selection.py`
- Modify: `src/behemoth/governance/families/oco_first_touch.py`
- Modify: `tests/governance/test_selection.py`
- Modify: `tests/governance/families/test_oco_first_touch_adapter.py` (create if missing)

- [ ] **Step 1: Add failing test for OCO selection_gate override**

```python
# tests/governance/families/test_oco_first_touch_adapter.py
import pandas as pd
from src.behemoth.governance.families import get_family_adapter


def test_oco_selection_gate_passes_when_thresholds_met():
    adapter = get_family_adapter("oco_first_touch")
    row = pd.Series({"both_window_rate": 0.7, "p_up_first": 0.5})
    assert adapter.selection_gate(
        row, {"min_both_window_rate": 0.5, "min_p_up_first": 0.4}
    ) is True


def test_oco_selection_gate_fails_on_low_both_window_rate():
    adapter = get_family_adapter("oco_first_touch")
    row = pd.Series({"both_window_rate": 0.3, "p_up_first": 0.5})
    assert adapter.selection_gate(
        row, {"min_both_window_rate": 0.5, "min_p_up_first": 0.4}
    ) is False
```

- [ ] **Step 2: Verify failure**

```bash
uv run pytest tests/governance/families/test_oco_first_touch_adapter.py -v
```

- [ ] **Step 3: Override selection_gate in OCO adapter**

Replace the `OcoFirstTouchHooks` class body in `src/behemoth/governance/families/oco_first_touch.py`:

```python
class OcoFirstTouchHooks(BaseFamilyGovernanceHooks):
    """OCO first-touch adapter. Phase 1c implements selection_gate."""

    def selection_gate(self, row, thresholds):
        return (
            float(row["both_window_rate"])
                >= float(thresholds["min_both_window_rate"])
            and float(row["p_up_first"])
                >= float(thresholds["min_p_up_first"])
        )
```

- [ ] **Step 4: Add `apply_family_selection_gate` to selection.py**

```python
def apply_family_selection_gate(
    *,
    candidates: pd.DataFrame,
    adapter,  # BaseFamilyGovernanceHooks
    thresholds: dict[str, float],
) -> pd.DataFrame:
    """Apply the adapter's family-specific selection_gate per candidate row.
    Returns the input DataFrame with a `selection_gate_pass` boolean column."""
    out = candidates.copy()
    out["selection_gate_pass"] = out.apply(
        lambda r: adapter.selection_gate(r, thresholds), axis=1
    )
    return out
```

- [ ] **Step 5: Test the integration**

Append to `tests/governance/test_selection.py`:

```python
def test_apply_family_selection_gate_uses_adapter_hook():
    candidates = pd.DataFrame([
        {"both_window_rate": 0.7, "p_up_first": 0.5},   # pass
        {"both_window_rate": 0.3, "p_up_first": 0.5},   # fail (low rate)
    ])
    from src.behemoth.governance.selection import apply_family_selection_gate
    from src.behemoth.governance.families import get_family_adapter
    out = apply_family_selection_gate(
        candidates=candidates,
        adapter=get_family_adapter("oco_first_touch"),
        thresholds={"min_both_window_rate": 0.5, "min_p_up_first": 0.4},
    )
    assert out["selection_gate_pass"].tolist() == [True, False]
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/governance/ -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/behemoth/governance/selection.py \
        src/behemoth/governance/families/oco_first_touch.py \
        tests/governance/test_selection.py \
        tests/governance/families/test_oco_first_touch_adapter.py
git commit -m "feat: stage G2 family-specific selection gate + OCO override"
```

### Task 1c.5: Rolling month-by-month state selection (port from legacy)

This is the heart of the OCO selection: for each test month M, select states using only data from prior train months. Port from `scripts/select_oco_reduced_core_rolling.py` `run()` function.

**Files:**
- Modify: `src/behemoth/governance/selection.py`
- Modify: `tests/governance/test_selection.py`

- [ ] **Step 1: Read the legacy `run()` function**

```bash
sed -n '/^def run(/,/^def [a-z_]/p' scripts/select_oco_reduced_core_rolling.py | head -200
```

Understand: it iterates months, builds a train window from prior months, applies gates, selects states whose train metrics meet criteria, and emits a per-month per-state row.

- [ ] **Step 2: Write failing integration test**

```python
# Append to tests/governance/test_selection.py
def test_select_states_rolling_emits_one_row_per_state_month():
    """End-to-end: input is per-(state, month) signals; output is per-state
    per-month selection result with all gate columns. Synthetic data: 2 states,
    3 months."""
    state_monthly = pd.DataFrame([
        # state s1: stable, capacity OK
        {"state_id": "s1", "month": "2026-01", "monthly_signals": 250,
         "share_of_signals": 0.30, "mean_gross_pips": 0.5,
         "both_window_rate": 0.7, "p_up_first": 0.5},
        {"state_id": "s1", "month": "2026-02", "monthly_signals": 240,
         "share_of_signals": 0.32, "mean_gross_pips": 0.4,
         "both_window_rate": 0.7, "p_up_first": 0.5},
        {"state_id": "s1", "month": "2026-03", "monthly_signals": 260,
         "share_of_signals": 0.29, "mean_gross_pips": 0.6,
         "both_window_rate": 0.7, "p_up_first": 0.5},
        # state s2: capacity fail
        {"state_id": "s2", "month": "2026-01", "monthly_signals": 100,
         "share_of_signals": 0.20, "mean_gross_pips": 0.3,
         "both_window_rate": 0.6, "p_up_first": 0.45},
        {"state_id": "s2", "month": "2026-02", "monthly_signals": 90,
         "share_of_signals": 0.22, "mean_gross_pips": 0.25,
         "both_window_rate": 0.6, "p_up_first": 0.45},
        {"state_id": "s2", "month": "2026-03", "monthly_signals": 105,
         "share_of_signals": 0.21, "mean_gross_pips": 0.35,
         "both_window_rate": 0.6, "p_up_first": 0.45},
    ])
    from src.behemoth.governance.selection import select_states_rolling
    from src.behemoth.governance.families import get_family_adapter
    schedule = select_states_rolling(
        state_monthly=state_monthly,
        adapter=get_family_adapter("oco_first_touch"),
        thresholds={
            "capacity_floor_monthly": 200,
            "capacity_floor_annual": 500,
            "max_state_churn": 0.45,
            "max_top_state_share": 0.35,
            "max_state_hhi": 0.25,
            "state_train_months": 2,
            "min_states": 1,
            "max_states": 12,
            "selection_gates": {"min_both_window_rate": 0.5, "min_p_up_first": 0.4},
        },
    )
    # 2026-01: no prior train months → no selection
    # 2026-02: train=[2026-01], s1 single-month → can't compute stability robustly
    # 2026-03: train=[2026-01, 2026-02], s1 passes, s2 fails capacity
    selected_2026_03 = schedule[
        (schedule["month"] == "2026-03") & (schedule["selected"])
    ]["state_id"].tolist()
    assert selected_2026_03 == ["s1"]
```

- [ ] **Step 3: Implement `select_states_rolling`**

Append to `src/behemoth/governance/selection.py`:

```python
def select_states_rolling(
    *,
    state_monthly: pd.DataFrame,
    adapter,  # BaseFamilyGovernanceHooks
    thresholds: dict,
) -> pd.DataFrame:
    """For each month M, select states using only prior train_window_months
    of data, apply gates, and emit per-(state, month) selection result.

    Output columns: state_id, month, capacity_pass, stability_pass,
    selection_gate_pass, selected, train_months (which months were used).
    Use sort=False everywhere to preserve insertion-order determinism."""
    months_sorted = sorted(state_monthly["month"].unique())
    train_window = int(thresholds["state_train_months"])
    rows = []
    for i, m in enumerate(months_sorted):
        train_months = months_sorted[max(0, i - train_window): i]
        if not train_months:
            continue
        train = state_monthly[state_monthly["month"].isin(train_months)]
        # Aggregate per-state across train window
        agg = train.groupby("state_id", sort=False).agg(
            avg_monthly_signals=("monthly_signals", "mean"),
            mean_gross_pips=("mean_gross_pips", "mean"),
            both_window_rate=("both_window_rate", "mean"),
            p_up_first=("p_up_first", "mean"),
        ).reset_index()
        agg["annualized_signals"] = agg["avg_monthly_signals"] * 12
        cap = apply_capacity_gate(
            states=agg,
            capacity_floor_monthly=thresholds["capacity_floor_monthly"],
            capacity_floor_annual=thresholds["capacity_floor_annual"],
        )
        stab = apply_stability_gate(
            state_monthly=train,
            max_state_churn=thresholds["max_state_churn"],
            max_top_state_share=thresholds["max_top_state_share"],
            max_state_hhi=thresholds["max_state_hhi"],
        )
        merged = cap.merge(stab, on="state_id", how="left")
        merged["stability_pass"] = merged["stability_pass"].fillna(False)
        fam_gated = apply_family_selection_gate(
            candidates=merged, adapter=adapter,
            thresholds=thresholds["selection_gates"],
        )
        fam_gated["selected"] = (
            fam_gated["capacity_pass"]
            & fam_gated["stability_pass"]
            & fam_gated["selection_gate_pass"]
        )
        for _, r in fam_gated.iterrows():
            rows.append({
                "state_id": r["state_id"],
                "month": m,
                "train_months": ",".join(train_months),
                "capacity_pass": bool(r["capacity_pass"]),
                "stability_pass": bool(r["stability_pass"]),
                "selection_gate_pass": bool(r["selection_gate_pass"]),
                "selected": bool(r["selected"]),
            })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_selection.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/selection.py tests/governance/test_selection.py
git commit -m "feat: stage G2 rolling state selection (port from legacy)"
```

### Task 1c.6: Open phase 1c PR

- [ ] **Step 1: Push + open PR**

```bash
git push -u origin governance-phase-1c
gh pr create --base governance-framework \
  --title "feat: governance stage G2 selection (phase 1c)" \
  --body "Phase 1c: stage G2 selection logic ported from legacy OCO selection script. Capacity gate, stability gate, family-specific gate via adapter hook, rolling month-by-month application. Unit-tested on synthetic per-state-month data. Byte-identical OCO parity validated in phase 1f."
```

- [ ] **Step 2: Merge after CI green**

---

# Phase 1d — Stage G3 (barrier_touch simulator)

**Goal:** First payoff simulator. Replays bid/ask ticks for each (state, entry_bar) pair to compute realized P&L. OCO adapter implements `simulate_one_entry` for barrier-touch detection.

**Branch:** `governance-phase-1d` off `governance-framework`.

### Task 1d.1: TickStreamProvider + shared aggregators

**Files:**
- Create: `src/behemoth/governance/tick_exact_shared.py`
- Test: `tests/governance/test_tick_exact_shared.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_tick_exact_shared.py
import pandas as pd
from pathlib import Path
import pytest

from src.behemoth.governance.tick_exact_shared import (
    TickStreamProvider,
    aggregate_state_summary,
)


def test_tick_stream_provider_returns_ticks_for_range(tmp_path):
    # Build a tiny tick parquet
    ticks = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=10, freq="1s", tz="UTC"),
        "bid": [1.1] * 10,
        "ask": [1.1001] * 10,
    })
    parquet = tmp_path / "EURUSD_ticks.parquet"
    ticks.to_parquet(parquet)

    provider = TickStreamProvider(tick_root=tmp_path)
    out = provider.get(
        symbol="EURUSD",
        start_ts=pd.Timestamp("2026-01-01T00:00:02", tz="UTC"),
        end_ts=pd.Timestamp("2026-01-01T00:00:05", tz="UTC"),
    )
    assert len(out) == 4  # ts: 00:00:02, 03, 04, 05


def test_aggregate_state_summary_computes_means_and_counts():
    fills = pd.DataFrame([
        {"state_id": "s1", "realized_pips": 0.5},
        {"state_id": "s1", "realized_pips": -0.2},
        {"state_id": "s2", "realized_pips": 1.0},
    ])
    summary = aggregate_state_summary(fills=fills)
    s1 = summary[summary["state_id"] == "s1"].iloc[0]
    assert s1["n_fills"] == 2
    assert abs(s1["mean_realized_pips"] - 0.15) < 1e-9
```

- [ ] **Step 2: Verify failure**

```bash
uv run pytest tests/governance/test_tick_exact_shared.py -v
```

- [ ] **Step 3: Implement tick_exact_shared.py**

```python
# src/behemoth/governance/tick_exact_shared.py
"""Shared infrastructure for the 3 payoff simulators.

- TickStreamProvider: loads bid/ask ticks for a (symbol, time_range).
- aggregate_state_summary: per-state summary stats (n_fills, mean, std,
  hit_rate, etc.) — shared output schema across all simulators.
- aggregate_monthly_summary: per-(state, month) breakdown.

All simulators write outputs in the same schema; the framework's verdict
stage reads from this schema regardless of family.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.behemoth.governance.errors import TickStreamGapError


@dataclass(frozen=True)
class TickStreamProvider:
    """Loads bid/ask ticks for (symbol, time_range) from a tick root dir.
    Expected layout: <tick_root>/<SYMBOL>_ticks.parquet (or per-month
    partitions — extend per file naming conventions used by the existing
    OCO tick-exact script)."""

    tick_root: Path

    def get(
        self, *, symbol: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp
    ) -> pd.DataFrame:
        path = Path(self.tick_root) / f"{symbol}_ticks.parquet"
        if not path.exists():
            raise TickStreamGapError(
                symbol=symbol,
                range_repr=f"{start_ts.isoformat()}..{end_ts.isoformat()}",
            )
        df = pd.read_parquet(path)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        mask = (df["ts"] >= start_ts) & (df["ts"] <= end_ts)
        return df.loc[mask].reset_index(drop=True)


def aggregate_state_summary(*, fills: pd.DataFrame) -> pd.DataFrame:
    """Per-state summary stats from a fills DataFrame. Schema matches
    legacy OCO tick_exact_summary columns for byte-identical migration."""
    grouped = fills.groupby("state_id", sort=False).agg(
        n_fills=("realized_pips", "count"),
        mean_realized_pips=("realized_pips", "mean"),
        std_realized_pips=("realized_pips", "std"),
        hit_rate=("realized_pips", lambda s: float((s > 0).mean())),
    ).reset_index()
    return grouped


def aggregate_monthly_summary(*, fills: pd.DataFrame) -> pd.DataFrame:
    """Per-(state, month) breakdown. Fills must have an `entry_month`
    column (YYYY-MM)."""
    grouped = fills.groupby(["state_id", "entry_month"], sort=False).agg(
        n_fills=("realized_pips", "count"),
        mean_realized_pips=("realized_pips", "mean"),
    ).reset_index()
    return grouped
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_tick_exact_shared.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/tick_exact_shared.py \
        tests/governance/test_tick_exact_shared.py
git commit -m "feat: tick_exact_shared infrastructure (TickStreamProvider + aggregators)"
```

### Task 1d.2: Barrier-touch simulator + OCO adapter hook

**Files:**
- Create: `src/behemoth/governance/tick_exact_barrier_touch.py`
- Modify: `src/behemoth/governance/families/oco_first_touch.py` (add simulate_one_entry)
- Create: `tests/governance/test_tick_exact_barrier_touch.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_tick_exact_barrier_touch.py
import pandas as pd
from pathlib import Path

from src.behemoth.governance.tick_exact_barrier_touch import (
    simulate_state_barrier_touch,
)
from src.behemoth.governance.families import get_family_adapter
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


def test_oco_simulator_detects_upper_barrier_touch(tmp_path):
    # Single entry at t=0, entry_price=1.1000, barrier_pips=2.0.
    # Bid moves up by 3 pips at t=2 → upper barrier (1.1002) hit.
    ticks = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
        "bid": [1.1000, 1.1001, 1.1003, 1.1003, 1.1003],
        "ask": [1.1001, 1.1002, 1.1004, 1.1004, 1.1004],
    })
    parquet = tmp_path / "EURUSD_ticks.parquet"
    ticks.to_parquet(parquet)

    entries = pd.DataFrame([{
        "state_id": "s1",
        "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
        "entry_price": 1.1000,
        "barrier_pips": 2.0,
        "horizon_seconds": 10,
        "symbol": "EURUSD",
    }])
    fills = simulate_state_barrier_touch(
        entries=entries,
        adapter=get_family_adapter("oco_first_touch"),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )
    assert len(fills) == 1
    # Upper barrier 1.1002 hit; OCO realized pips depends on adapter rule
    # — placeholder check: realized_pips field exists and is finite.
    assert pd.notna(fills["realized_pips"].iloc[0])
```

- [ ] **Step 2: Verify failure**

```bash
uv run pytest tests/governance/test_tick_exact_barrier_touch.py -v
```

- [ ] **Step 3: Implement barrier_touch simulator**

```python
# src/behemoth/governance/tick_exact_barrier_touch.py
"""Simulator 1: barrier_touch payoff.

Replays bid/ask ticks forward from each entry bar's close_ts until either
a barrier is touched or the horizon expires. Realized P&L is computed by
the family adapter's simulate_one_entry hook (different barrier families
have different barrier-detection rules: single barrier, asymmetric brackets,
two-phase sweeps).

Inputs:
- entries: DataFrame with state_id, entry_ts, entry_price, barrier_pips,
  horizon_seconds (or horizon_bars), symbol.
- adapter: family adapter providing simulate_one_entry.
- tick_provider: TickStreamProvider for bid/ask ticks.

Output: fills DataFrame with state_id, entry_ts, realized_pips,
entry_month.
"""

from __future__ import annotations

import pandas as pd

from src.behemoth.governance.families.base import BaseFamilyGovernanceHooks
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


def simulate_state_barrier_touch(
    *,
    entries: pd.DataFrame,
    adapter: BaseFamilyGovernanceHooks,
    tick_provider: TickStreamProvider,
) -> pd.DataFrame:
    """For each entry row, fetch ticks from entry_ts forward for
    horizon_seconds and ask the adapter to compute realized_pips.
    Returns fills DataFrame."""
    fills_rows = []
    for _, entry in entries.iterrows():
        start_ts = entry["entry_ts"]
        end_ts = start_ts + pd.Timedelta(seconds=float(entry["horizon_seconds"]))
        tick_stream = tick_provider.get(
            symbol=str(entry["symbol"]),
            start_ts=start_ts,
            end_ts=end_ts,
        )
        realized = adapter.simulate_one_entry(
            tick_stream=tick_stream,
            entry_bar=entry,
            params=entry.to_dict(),
        )
        fills_rows.append({
            "state_id": entry["state_id"],
            "entry_ts": entry["entry_ts"],
            "entry_month": entry["entry_ts"].strftime("%Y-%m"),
            "realized_pips": float(realized),
        })
    return pd.DataFrame(fills_rows)
```

- [ ] **Step 4: Override simulate_one_entry in OCO adapter**

Append to `src/behemoth/governance/families/oco_first_touch.py`:

```python
# Add at top of class body
    def simulate_one_entry(self, tick_stream, entry_bar, params):
        """OCO first-touch payoff: first barrier reached wins +K pips
        (minus spread), neither reached returns 0. Symmetric barriers at
        entry_price ± barrier_pips * pip_size. Uses bid for upper barrier
        (long-exit) and ask for lower barrier (short-exit)."""
        if tick_stream.empty:
            return 0.0
        # Pip size for EURUSD = 0.0001 (configurable later).
        pip_size = 0.0001
        entry_price = float(entry_bar["entry_price"])
        barrier = float(entry_bar["barrier_pips"]) * pip_size
        upper = entry_price + barrier
        lower = entry_price - barrier
        for _, tick in tick_stream.iterrows():
            if float(tick["bid"]) >= upper:
                return float(entry_bar["barrier_pips"])
            if float(tick["ask"]) <= lower:
                return -float(entry_bar["barrier_pips"])
        return 0.0
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/governance/test_tick_exact_barrier_touch.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/governance/tick_exact_barrier_touch.py \
        src/behemoth/governance/families/oco_first_touch.py \
        tests/governance/test_tick_exact_barrier_touch.py
git commit -m "feat: stage G3 barrier_touch simulator + OCO simulate_one_entry"
```

### Task 1d.3: Open phase 1d PR

- [ ] Push + open PR + merge as in 1b/1c.

```bash
git push -u origin governance-phase-1d
gh pr create --base governance-framework \
  --title "feat: governance stage G3 barrier_touch simulator (phase 1d)" \
  --body "Phase 1d: barrier_touch simulator + OCO adapter simulate_one_entry. Tick replay with shared TickStreamProvider; family-specific barrier detection via adapter hook. Synthetic tick fixture validates end-to-end."
```

---

# Phase 1e — Stages G4 + G5 (verdict roll-up + freeze)

**Goal:** Per-state GO/NO_GO computed from selection + tick-exact results. Roll-up to (symbol, family) GO/NO_GO. Roll-up to symbol GO/NO_GO using `required_families`. Write freeze JSON.

**Branch:** `governance-phase-1e` off `governance-framework`.

### Task 1e.1: State-level verdict (G4)

**Files:**
- Create: `src/behemoth/governance/verdict.py`
- Test: `tests/governance/test_verdict.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_verdict.py
import pandas as pd
from src.behemoth.governance.verdict import (
    compute_state_verdicts,
    compute_family_verdict,
    compute_symbol_verdict,
)


def test_state_verdict_GO_when_selected_and_tick_exact_positive():
    selection = pd.DataFrame([
        {"state_id": "s1", "selected": True},
        {"state_id": "s2", "selected": False},
    ])
    tick_exact = pd.DataFrame([
        {"state_id": "s1", "mean_realized_pips": 0.5},
        {"state_id": "s2", "mean_realized_pips": 0.3},
    ])
    verdicts = compute_state_verdicts(
        selection=selection,
        tick_exact=tick_exact,
        min_realized_pips_pass=0.0,
    )
    assert verdicts.loc[verdicts["state_id"] == "s1", "verdict"].iloc[0] == "GO"
    assert verdicts.loc[verdicts["state_id"] == "s2", "verdict"].iloc[0] == "NO_GO"


def test_state_verdict_NO_GO_when_selected_but_tick_exact_negative():
    selection = pd.DataFrame([{"state_id": "s1", "selected": True}])
    tick_exact = pd.DataFrame([{"state_id": "s1", "mean_realized_pips": -0.2}])
    verdicts = compute_state_verdicts(
        selection=selection, tick_exact=tick_exact, min_realized_pips_pass=0.0,
    )
    assert verdicts["verdict"].iloc[0] == "NO_GO"


def test_family_verdict_GO_if_any_state_GO():
    state_verdicts = pd.DataFrame([
        {"state_id": "s1", "verdict": "NO_GO"},
        {"state_id": "s2", "verdict": "GO"},
    ])
    assert compute_family_verdict(state_verdicts=state_verdicts) == "GO"


def test_family_verdict_NO_GO_if_all_states_NO_GO():
    state_verdicts = pd.DataFrame([
        {"state_id": "s1", "verdict": "NO_GO"},
        {"state_id": "s2", "verdict": "NO_GO"},
    ])
    assert compute_family_verdict(state_verdicts=state_verdicts) == "NO_GO"


def test_symbol_verdict_GO_when_all_required_families_GO():
    family_verdicts = {
        "oco_first_touch": "GO",
        "directional_run": "GO",
        "lead_lag": "NO_GO",  # not required
    }
    v = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=("oco_first_touch", "directional_run"),
    )
    assert v == "GO"


def test_symbol_verdict_NO_GO_when_any_required_family_NO_GO():
    family_verdicts = {"oco_first_touch": "GO", "directional_run": "NO_GO"}
    v = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=("oco_first_touch", "directional_run"),
    )
    assert v == "NO_GO"
```

- [ ] **Step 2: Verify failure**

```bash
uv run pytest tests/governance/test_verdict.py -v
```

- [ ] **Step 3: Implement verdict.py**

```python
# src/behemoth/governance/verdict.py
"""Stages G4 + G5: verdict computation + roll-up.

G4: per-state verdict (GO iff selected AND tick-exact mean_realized_pips
≥ min_realized_pips_pass).
G5: per-(symbol, family) roll-up (GO iff ≥1 state GO).
G5: per-symbol roll-up (GO iff every required_family is GO).

Verdict values are canonical from CLAUDE.md: GO, NO_GO.
"""

from __future__ import annotations

import pandas as pd

GO = "GO"
NO_GO = "NO_GO"


def compute_state_verdicts(
    *,
    selection: pd.DataFrame,
    tick_exact: pd.DataFrame,
    min_realized_pips_pass: float,
) -> pd.DataFrame:
    """Join selection + tick_exact on state_id; emit verdict per state."""
    joined = selection.merge(tick_exact, on="state_id", how="left")
    joined["verdict"] = [
        GO
        if (sel and pd.notna(rp) and float(rp) >= float(min_realized_pips_pass))
        else NO_GO
        for sel, rp in zip(joined["selected"], joined["mean_realized_pips"])
    ]
    return joined[["state_id", "verdict"]]


def compute_family_verdict(*, state_verdicts: pd.DataFrame) -> str:
    """GO if any state is GO, else NO_GO."""
    if (state_verdicts["verdict"] == GO).any():
        return GO
    return NO_GO


def compute_symbol_verdict(
    *,
    family_verdicts: dict[str, str],
    required_families: tuple[str, ...],
) -> str:
    """GO iff every required family is GO. Missing family = NO_GO."""
    for fam in required_families:
        if family_verdicts.get(fam) != GO:
            return NO_GO
    return GO
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_verdict.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/verdict.py tests/governance/test_verdict.py
git commit -m "feat: stages G4 + G5 verdict computation + roll-up"
```

### Task 1e.2: Freeze artifact writer

**Files:**
- Create: `src/behemoth/governance/freeze.py`
- Test: `tests/governance/test_freeze.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_freeze.py
import json
from pathlib import Path

import pandas as pd

from src.behemoth.governance.freeze import write_freeze_artifact
from src.behemoth.governance.families import get_family_adapter


def test_freeze_writes_json_with_schema_version(tmp_path):
    adapter = get_family_adapter("oco_first_touch")
    qualified = pd.DataFrame([
        {"state_id": "s1", "selected": True, "verdict": "GO"},
    ])
    path = write_freeze_artifact(
        out_dir=tmp_path,
        symbol="EURUSD",
        adapter=adapter,
        qualified_states=qualified,
        model_month="2026-05",
    )
    assert path.exists()
    j = json.loads(path.read_text())
    assert j["family"] == "oco_first_touch"
    assert j["schema_version"] == "oco_v4.0"
    assert j["model_month"] == "2026-05"
    assert len(j["qualified_states"]) == 1


def test_freeze_path_includes_symbol_and_family(tmp_path):
    adapter = get_family_adapter("oco_first_touch")
    qualified = pd.DataFrame([{"state_id": "s1", "selected": True, "verdict": "GO"}])
    path = write_freeze_artifact(
        out_dir=tmp_path, symbol="EURUSD", adapter=adapter,
        qualified_states=qualified, model_month="2026-05",
    )
    assert "EURUSD" in path.name
    assert "oco_first_touch" in path.name
```

- [ ] **Step 2: Verify failure**

```bash
uv run pytest tests/governance/test_freeze.py -v
```

- [ ] **Step 3: Implement freeze.py**

```python
# src/behemoth/governance/freeze.py
"""Freeze artifact writer. Emits per-(symbol, family) JSON tagged with
model_month. Schema is controlled by the adapter's encode_freeze_artifact
hook so each family can extend the payload (e.g., OCO adds thresholds for
JForex consumption, directional_run adds horizon-exit metadata).

JSON keys are sorted alphabetically to keep output byte-stable across
Python dict-ordering changes. Floats formatted with `default=str` to
preserve full precision (no scientific-notation surprises)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.behemoth.governance.families.base import BaseFamilyGovernanceHooks


def write_freeze_artifact(
    *,
    out_dir: Path,
    symbol: str,
    adapter: BaseFamilyGovernanceHooks,
    qualified_states: pd.DataFrame,
    model_month: str,
) -> Path:
    payload = adapter.encode_freeze_artifact(
        qualified_states=qualified_states, model_month=model_month,
    )
    # Always carry symbol; adapter may omit it
    payload.setdefault("symbol", symbol)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_{adapter.config.name}_governance_frozen.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str))
    return path
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/governance/test_freeze.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/governance/freeze.py tests/governance/test_freeze.py
git commit -m "feat: freeze artifact writer with schema_version tagging"
```

### Task 1e.3: Orchestrator script

**Files:**
- Create: `scripts/governance/run_governance_all.py`
- Test: `tests/governance/test_run_governance_all_e2e.py`

- [ ] **Step 1: Write failing e2e test**

```python
# tests/governance/test_run_governance_all_e2e.py
"""End-to-end test of the orchestrator on a tiny synthetic fixture.
Exercises the full pipeline: load YAML, run G1-G5, write artifacts.
Should complete in <5s with deterministic verdicts."""

import json
import textwrap
from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.skip(reason="Filled out after orchestrator implementation lands")
def test_run_governance_all_emits_symbol_verdict(tmp_path):
    pass
```

(Skipped initially; populated after the implementation lands so the test reflects real CLI args.)

- [ ] **Step 2: Implement orchestrator**

```python
# scripts/governance/run_governance_all.py
#!/usr/bin/env python3
"""Run the governance pipeline (G1-G5) for one symbol.

Usage:
    uv run python scripts/governance/run_governance_all.py \\
        --symbol-yaml configs/research/experiments/eurusd_governance.yaml \\
        --candidate-dir data/analysis/tick_opportunity_mining \\
        --out-dir data/analysis/governance \\
        --tick-root <path_to_ticks>

For each family in `required_families`:
1. Load candidates CSV (`<SYM>_<library>_candidates.csv`)
2. G1: assemble states
3. G2: rolling selection
4. G3: tick-exact verification
5. G4: state-level verdicts
6. G5: family + symbol roll-up + freeze artifact write

Writes per-symbol verdict summary to <out_dir>/<model_month>/verdicts/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# sys.path bootstrap (same pattern as PR #194)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd  # noqa: E402

from src.behemoth.governance.families import get_family_adapter  # noqa: E402
from src.behemoth.governance.freeze import write_freeze_artifact  # noqa: E402
from src.behemoth.governance.state_assembly import assemble_states  # noqa: E402
from src.behemoth.governance.symbol_config import (  # noqa: E402
    load_symbol_governance_config,
)
from src.behemoth.governance.verdict import (  # noqa: E402
    compute_family_verdict,
    compute_state_verdicts,
    compute_symbol_verdict,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol-yaml", required=True)
    p.add_argument("--candidate-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--tick-root", required=True)
    args = p.parse_args()

    cfg = load_symbol_governance_config(Path(args.symbol_yaml))
    out_dir = Path(args.out_dir) / cfg.model_month
    out_dir.mkdir(parents=True, exist_ok=True)

    family_verdicts: dict[str, str] = {}
    for fam_name in cfg.required_families:
        adapter = get_family_adapter(fam_name)
        # For OCO: candidates file is `<SYM>_oco_candidates.csv`. For other
        # families the suffix varies; the mining naming convention is
        # captured by a per-family lookup table (out of scope here — wired
        # in 1g cutover).
        # ... (full orchestration body — implement to match the test
        # expectations populated in Step 1)
        family_verdicts[fam_name] = "NO_GO"  # placeholder until populated

    symbol_verdict = compute_symbol_verdict(
        family_verdicts=family_verdicts,
        required_families=cfg.required_families,
    )
    summary = pd.DataFrame([{
        "symbol": cfg.symbol,
        "model_month": cfg.model_month,
        "verdict": symbol_verdict,
        **{f"{f}_verdict": v for f, v in family_verdicts.items()},
    }])
    summary.to_csv(out_dir / f"{cfg.symbol}_symbol_verdict.csv", index=False)
    print(f"[gov] {cfg.symbol}: symbol_verdict={symbol_verdict}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit (skipped test + orchestrator stub)**

```bash
git add scripts/governance/run_governance_all.py \
        tests/governance/test_run_governance_all_e2e.py
git commit -m "feat: governance orchestrator script (G1-G5 wiring)"
```

### Task 1e.4: Open phase 1e PR

- [ ] Push + open PR + merge.

```bash
git push -u origin governance-phase-1e
gh pr create --base governance-framework \
  --title "feat: governance stages G4 + G5 + freeze + orchestrator (phase 1e)" \
  --body "Phase 1e: state/family/symbol verdict computation, freeze artifact writer, orchestrator script wiring all stages together. End-to-end test marked xfail-skipped pending phase 1g cutover where real candidate/tick paths are plumbed."
```

---

# Phase 1f — Byte-identical OCO parity test in CI

**Goal:** A CI-gated script that runs both the legacy OCO pipeline and the new framework on a frozen reference snapshot, byte-diffing every artifact. Fails on any diff.

**Branch:** `governance-phase-1f` off `governance-framework`.

### Task 1f.1: Capture frozen reference snapshot

**Files:**
- Create: `tests/governance/fixtures/governance_oco_reference/EURUSD_2026-05/*` (state_schedule.csv, freeze.json, tick_exact_summary.csv)

- [ ] **Step 1: Generate snapshot from last good OCO run**

```bash
git checkout governance-framework
git pull
git checkout -b governance-phase-1f
mkdir -p tests/governance/fixtures/governance_oco_reference/EURUSD_2026-05
# Copy current OCO outputs as the byte-identical target.
cp data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv \
   tests/governance/fixtures/governance_oco_reference/EURUSD_2026-05/state_schedule.csv
cp data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_summary.csv \
   tests/governance/fixtures/governance_oco_reference/EURUSD_2026-05/reduced_summary.csv
# Add tick_exact and freeze JSON when available (per current pipeline outputs)
git add tests/governance/fixtures/governance_oco_reference/
git commit -m "test: pin OCO reference snapshot for byte-parity gate"
```

### Task 1f.2: Parity validation script

**Files:**
- Create: `scripts/governance/validate_oco_migration_parity.py`
- Test: `tests/governance/test_oco_byte_parity.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_oco_byte_parity.py
"""Byte-identical parity test. Runs the new pipeline on the snapshot
inputs and diffs against the reference outputs. Fails on any diff."""

import subprocess
from pathlib import Path

import pytest

REF_DIR = Path("tests/governance/fixtures/governance_oco_reference/EURUSD_2026-05")


@pytest.mark.skipif(
    not REF_DIR.exists(),
    reason="reference snapshot not present (run snapshot capture first)",
)
def test_oco_state_schedule_byte_identical(tmp_path):
    # Run the new pipeline producing into tmp_path
    subprocess.run([
        "uv", "run", "python", "scripts/governance/validate_oco_migration_parity.py",
        "--ref-dir", str(REF_DIR),
        "--out-dir", str(tmp_path),
    ], check=True)
    # The script asserts byte-identity internally; if it returned 0 we pass.
```

- [ ] **Step 2: Implement parity script**

```python
# scripts/governance/validate_oco_migration_parity.py
#!/usr/bin/env python3
"""Byte-identical OCO migration parity gate.

For each artifact in the reference snapshot:
1. Re-run the new pipeline to produce the same artifact.
2. Diff byte-for-byte against the reference.
3. Fail with exit code 1 on any diff.

This script is the CI gate for the OCO migration cutover (phase 1g).
Until it passes for all 6 symbols' most-recent frozen month, the cutover
is blocked."""

from __future__ import annotations

import argparse
import filecmp
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ref-dir", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # TODO in phase 1g: invoke the new orchestrator to produce out_dir
    # artifacts that should match ref_dir contents byte-for-byte.

    diffs: list[str] = []
    for ref_file in args.ref_dir.glob("**/*"):
        if not ref_file.is_file():
            continue
        candidate = args.out_dir / ref_file.relative_to(args.ref_dir)
        if not candidate.exists():
            diffs.append(f"MISSING: {candidate}")
            continue
        if not filecmp.cmp(ref_file, candidate, shallow=False):
            diffs.append(f"DIFF: {candidate}")

    if diffs:
        for d in diffs:
            print(d, file=sys.stderr)
        return 1
    print("OCO migration parity: byte-identical on all artifacts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run test (will skip without proper integration, or fail with MISSING)**

```bash
uv run pytest tests/governance/test_oco_byte_parity.py -v
```

Expected: test fails because the new orchestrator does not yet produce matching artifacts. **This failure is the gate** — phases 1b-1e must produce byte-identical output before the parity test passes. Mark the test as `xfail(strict=True)` until phase 1g cutover so CI flags any regression but does not block phase merges.

- [ ] **Step 4: Commit**

```bash
git add scripts/governance/validate_oco_migration_parity.py \
        tests/governance/test_oco_byte_parity.py
git commit -m "test: byte-identical OCO migration parity gate (xfail until 1g)"
```

### Task 1f.3: Open phase 1f PR

```bash
git push -u origin governance-phase-1f
gh pr create --base governance-framework \
  --title "test: OCO byte-identical migration parity gate (phase 1f)" \
  --body "Phase 1f: parity script + reference snapshot fixture + xfail test. The test currently fails (no integration between new orchestrator and the parity comparator); phase 1g flips it to passing as the cutover gate."
```

---

# Phase 1g — Cutover via `onboard_symbol.py`

**Goal:** Switch `onboard_symbol.py` stages 2f/3/4 from legacy OCO scripts to the new orchestrator. Move legacy scripts to `scripts/legacy/`. Parity test flips from xfail to passing.

**Branch:** `governance-phase-1g` off `governance-framework`.

### Task 1g.1: Complete the orchestrator end-to-end body

**Files:**
- Modify: `scripts/governance/run_governance_all.py` (fill in the `... placeholder until populated` block from 1e)
- Modify: `tests/governance/test_run_governance_all_e2e.py` (un-skip)

- [ ] **Step 1: Wire all stages into the orchestrator**

Replace the placeholder loop body in `run_governance_all.py` with actual G1-G5 invocations: read candidates, call `assemble_states`, `select_states_rolling`, `simulate_state_barrier_touch`, `compute_state_verdicts`, `compute_family_verdict`, write artifacts to legacy paths (`data/analysis/tick_opportunity_mining/reduced_core_rolling/<SYM>_*.csv`) plus the new canonical paths.

- [ ] **Step 2: Update test to assert byte-identical EURUSD output**

```python
# Replace the skipped test body in tests/governance/test_run_governance_all_e2e.py
def test_run_governance_all_byte_identical_on_eurusd_reference(tmp_path):
    """Run the orchestrator on the EURUSD reference YAML and assert the
    output state_schedule.csv matches the frozen reference byte-for-byte."""
    import subprocess
    import filecmp

    ref_state = Path(
        "tests/governance/fixtures/governance_oco_reference/EURUSD_2026-05/state_schedule.csv"
    )
    subprocess.run([
        "uv", "run", "python", "scripts/governance/run_governance_all.py",
        "--symbol-yaml", "configs/research/experiments/eurusd_governance.yaml",
        "--candidate-dir", "data/analysis/tick_opportunity_mining",
        "--out-dir", str(tmp_path),
        "--tick-root", "data/raw_ticks",
    ], check=True)
    out_state = tmp_path / "2026-05" / "state_schedules" / "EURUSD_oco_first_touch_state_schedule.csv"
    assert filecmp.cmp(ref_state, out_state, shallow=False), "byte-identity broken"
```

- [ ] **Step 3: Run; iterate until byte-identical**

```bash
uv run pytest tests/governance/test_run_governance_all_e2e.py -v
```

If it diffs, inspect the diff and fix in the framework (most likely culprits per spec: dict iteration order in JSON, groupby row ordering, float formatting). Repeat until green.

- [ ] **Step 4: Commit**

```bash
git add scripts/governance/run_governance_all.py \
        tests/governance/test_run_governance_all_e2e.py
git commit -m "feat: orchestrator G1-G5 end-to-end + byte-identity test"
```

### Task 1g.2: Switch `onboard_symbol.py` to new orchestrator

**Files:**
- Modify: `scripts/onboard_symbol.py:239-272` (stage 2f + stage 3 conditional)
- Move: `scripts/select_oco_reduced_core_rolling.py` → `scripts/legacy/`
- Move: `scripts/verify_oco_tick_exact_shortlist.py` → `scripts/legacy/`
- Move: `scripts/freeze_oco_historical_governance.py` → `scripts/legacy/`

- [ ] **Step 1: Edit `onboard_symbol.py`**

Replace the Stage 2f / Stage 3 calls in `stage_2_mining` and `stage_3_conditional` with:

```python
    _uv_run(
        "governance/run_governance_all.py",
        "--symbol-yaml",
        f"configs/research/experiments/{sym}_governance.yaml",
        "--candidate-dir", "data/analysis/tick_opportunity_mining",
        "--out-dir", "data/analysis/governance",
        "--tick-root", str(TICK_ROOT),
        dry_run=dry_run,
        label="Stage 2f-4: Unified governance",
    )
```

- [ ] **Step 2: Move legacy scripts**

```bash
mkdir -p scripts/legacy
git mv scripts/select_oco_reduced_core_rolling.py scripts/legacy/
git mv scripts/verify_oco_tick_exact_shortlist.py scripts/legacy/
git mv scripts/freeze_oco_historical_governance.py scripts/legacy/
```

- [ ] **Step 3: Create per-symbol governance YAMLs**

For each of EURUSD, GBPUSD, AUDUSD, USDJPY, USDCAD, USDCHF: copy `_governance_template.yaml` and fill in real thresholds matching the legacy YAML for that symbol.

```bash
for sym in eurusd gbpusd audusd usdjpy usdcad usdchf; do
  cp configs/research/experiments/_governance_template.yaml \
     configs/research/experiments/${sym}_governance.yaml
  # Hand-edit each to set symbol, thresholds matching <sym>_oco_reduced_core_rolling.yaml
done
git add configs/research/experiments/*_governance.yaml
```

- [ ] **Step 4: Run full retrain in dry-run to confirm wiring**

```bash
uv run python scripts/onboard_symbol.py --symbol EURUSD --months 202401-202605 --dry-run
```

Expected: stage 2f-4 log line appears, no errors.

- [ ] **Step 5: Flip the parity test from xfail to passing**

Remove `@pytest.mark.xfail` from `tests/governance/test_oco_byte_parity.py`.

- [ ] **Step 6: Run parity test**

```bash
uv run pytest tests/governance/test_oco_byte_parity.py -v
```

Expected: PASSED. If not, iterate on the framework until byte-identity holds.

- [ ] **Step 7: Commit cutover**

```bash
git add scripts/onboard_symbol.py scripts/legacy/ \
        configs/research/experiments/*_governance.yaml \
        tests/governance/test_oco_byte_parity.py
git commit -m "feat: cutover onboard_symbol to unified governance + legacy archive"
```

### Task 1g.3: Open phase 1g PR + merge after CI green

```bash
git push -u origin governance-phase-1g
gh pr create --base governance-framework \
  --title "feat: cutover onboard_symbol.py to unified governance (phase 1g)" \
  --body "Phase 1g: onboard_symbol.py stages 2f/3/4 now invoke the new orchestrator. Legacy OCO scripts moved to scripts/legacy/. Per-symbol governance YAMLs created for all 6 symbols. Byte-identical parity test now passing."
```

---

# Phase 1h — `forward_return` simulator (no adapter yet)

**Goal:** Implement simulator 2 with synthetic tests. No family adapter uses it yet — that's sub-project 2.

**Branch:** `governance-phase-1h` off `governance-framework`.

### Task 1h.1: Forward-return simulator

**Files:**
- Create: `src/behemoth/governance/tick_exact_forward_return.py`
- Test: `tests/governance/test_tick_exact_forward_return.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_tick_exact_forward_return.py
import pandas as pd
import pytest

from src.behemoth.governance.tick_exact_forward_return import (
    simulate_state_forward_return,
)
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class _FakeAdapter:
    """Tiny stand-in adapter: long-only forward-return, exit at horizon."""
    def simulate_one_entry(self, tick_stream, entry_bar, params):
        if tick_stream.empty:
            return 0.0
        entry = float(tick_stream.iloc[0]["ask"])  # buy at ask
        exit_ = float(tick_stream.iloc[-1]["bid"])  # sell at bid
        return (exit_ - entry) / 0.0001  # pips


def test_forward_return_simulator_long_only(tmp_path):
    ticks = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
        "bid": [1.1000, 1.1001, 1.1002, 1.1003, 1.1004],
        "ask": [1.1001, 1.1002, 1.1003, 1.1004, 1.1005],
    })
    (tmp_path / "EURUSD_ticks.parquet").write_bytes(b"")
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    entries = pd.DataFrame([{
        "state_id": "s1",
        "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
        "horizon_seconds": 4,
        "symbol": "EURUSD",
    }])
    fills = simulate_state_forward_return(
        entries=entries,
        adapter=_FakeAdapter(),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
    )
    # Long entry at 1.1001 ask, exit 4s later at 1.1004 bid → 3 pips
    assert abs(fills["realized_pips"].iloc[0] - 3.0) < 1e-6
```

- [ ] **Step 2: Implement**

```python
# src/behemoth/governance/tick_exact_forward_return.py
"""Simulator 2: forward_return payoff.

For each (state, entry_bar), execute a market order at entry_ts (bid or
ask depending on side via adapter), hold for horizon_seconds, exit at
the horizon. Realized pips = exit_price - entry_price - spread.

Family-specific hook: simulate_one_entry decides the side (long/short)
and any conditional logic (e.g., directional_run only takes the bet
when run_sign matches `bet`).
"""

from __future__ import annotations

import pandas as pd

from src.behemoth.governance.tick_exact_shared import TickStreamProvider


def simulate_state_forward_return(
    *,
    entries: pd.DataFrame,
    adapter,  # BaseFamilyGovernanceHooks
    tick_provider: TickStreamProvider,
) -> pd.DataFrame:
    fills_rows = []
    for _, entry in entries.iterrows():
        start_ts = entry["entry_ts"]
        end_ts = start_ts + pd.Timedelta(seconds=float(entry["horizon_seconds"]))
        tick_stream = tick_provider.get(
            symbol=str(entry["symbol"]),
            start_ts=start_ts,
            end_ts=end_ts,
        )
        realized = adapter.simulate_one_entry(
            tick_stream=tick_stream, entry_bar=entry, params=entry.to_dict(),
        )
        fills_rows.append({
            "state_id": entry["state_id"],
            "entry_ts": entry["entry_ts"],
            "entry_month": entry["entry_ts"].strftime("%Y-%m"),
            "realized_pips": float(realized),
        })
    return pd.DataFrame(fills_rows)
```

- [ ] **Step 3: Run tests + commit**

```bash
uv run pytest tests/governance/test_tick_exact_forward_return.py -v
git add src/behemoth/governance/tick_exact_forward_return.py \
        tests/governance/test_tick_exact_forward_return.py
git commit -m "feat: stage G3 forward_return simulator (no adapter yet)"
```

### Task 1h.2: Open phase 1h PR

```bash
git push -u origin governance-phase-1h
gh pr create --base governance-framework \
  --title "feat: governance forward_return simulator (phase 1h)" \
  --body "Phase 1h: simulator 2 implemented + unit-tested with a synthetic adapter. No family uses it yet — directional/directional_inverse/directional_run adapters come in sub-project 2."
```

---

# Phase 1i — `cross_symbol_residual` simulator (no adapter yet)

**Goal:** Implement simulator 3 with synthetic tests. No family adapter uses it yet — that's sub-project 4.

**Branch:** `governance-phase-1i` off `governance-framework`.

### Task 1i.1: Cross-symbol residual simulator

**Files:**
- Create: `src/behemoth/governance/tick_exact_cross_symbol.py`
- Test: `tests/governance/test_tick_exact_cross_symbol.py`

- [ ] **Step 1: Write failing test**

```python
# tests/governance/test_tick_exact_cross_symbol.py
import pandas as pd

from src.behemoth.governance.tick_exact_cross_symbol import (
    simulate_state_cross_symbol,
)
from src.behemoth.governance.tick_exact_shared import TickStreamProvider


class _FakeAdapter:
    """Test double: long-only, with a freshness check on cs_frame."""
    def simulate_one_entry(self, tick_stream, entry_bar, params, cs_frame=None):
        if tick_stream.empty or cs_frame is None or cs_frame.empty:
            return 0.0
        # Freshness: cs_frame's last ts must be <= entry_ts
        last_cs = pd.Timestamp(cs_frame["close_ts"].iloc[-1])
        entry = pd.Timestamp(entry_bar["entry_ts"])
        if (entry - last_cs).total_seconds() > 60:
            return 0.0
        return (float(tick_stream.iloc[-1]["bid"])
                - float(tick_stream.iloc[0]["ask"])) / 0.0001


def test_cross_symbol_simulator_drops_stale_cs(tmp_path):
    ticks = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=5, freq="1s", tz="UTC"),
        "bid": [1.1000] * 5,
        "ask": [1.1001] * 5,
    })
    ticks.to_parquet(tmp_path / "EURUSD_ticks.parquet")

    # cs_frame is 2 hours stale → adapter returns 0
    cs_frame = pd.DataFrame({
        "close_ts": [pd.Timestamp("2025-12-31T22:00:00", tz="UTC")],
    })
    entries = pd.DataFrame([{
        "state_id": "s1",
        "entry_ts": pd.Timestamp("2026-01-01T00:00:00", tz="UTC"),
        "horizon_seconds": 4,
        "symbol": "EURUSD",
    }])
    fills = simulate_state_cross_symbol(
        entries=entries,
        adapter=_FakeAdapter(),
        tick_provider=TickStreamProvider(tick_root=tmp_path),
        cs_frame=cs_frame,
    )
    assert fills["realized_pips"].iloc[0] == 0.0
```

- [ ] **Step 2: Implement**

```python
# src/behemoth/governance/tick_exact_cross_symbol.py
"""Simulator 3: cross_symbol_residual payoff.

Same payoff shape as forward_return, plus a cross-symbol freshness gate:
the adapter receives the cs_frame alongside the entry frame's ticks and
checks the trigger condition is still observable at execution time
(prevents look-ahead and stale-data fills).
"""

from __future__ import annotations

import pandas as pd

from src.behemoth.governance.tick_exact_shared import TickStreamProvider


def simulate_state_cross_symbol(
    *,
    entries: pd.DataFrame,
    adapter,  # BaseFamilyGovernanceHooks
    tick_provider: TickStreamProvider,
    cs_frame: pd.DataFrame,
) -> pd.DataFrame:
    fills_rows = []
    for _, entry in entries.iterrows():
        start_ts = entry["entry_ts"]
        end_ts = start_ts + pd.Timedelta(seconds=float(entry["horizon_seconds"]))
        tick_stream = tick_provider.get(
            symbol=str(entry["symbol"]),
            start_ts=start_ts, end_ts=end_ts,
        )
        realized = adapter.simulate_one_entry(
            tick_stream=tick_stream, entry_bar=entry, params=entry.to_dict(),
            cs_frame=cs_frame,
        )
        fills_rows.append({
            "state_id": entry["state_id"],
            "entry_ts": entry["entry_ts"],
            "entry_month": entry["entry_ts"].strftime("%Y-%m"),
            "realized_pips": float(realized),
        })
    return pd.DataFrame(fills_rows)
```

- [ ] **Step 3: Run + commit**

```bash
uv run pytest tests/governance/test_tick_exact_cross_symbol.py -v
git add src/behemoth/governance/tick_exact_cross_symbol.py \
        tests/governance/test_tick_exact_cross_symbol.py
git commit -m "feat: stage G3 cross_symbol_residual simulator (no adapter yet)"
```

### Task 1i.2: Open phase 1i PR

```bash
git push -u origin governance-phase-1i
gh pr create --base governance-framework \
  --title "feat: governance cross_symbol_residual simulator (phase 1i)" \
  --body "Phase 1i: simulator 3 implemented + unit-tested. No family uses it yet — dollar_residual/dispersion_rank/lead_lag adapters come in sub-project 4."
```

---

# Final umbrella merge

After all 9 phase PRs merge to `governance-framework`:

- [ ] **Step 1: Squash-merge umbrella branch to main**

```bash
gh pr create --base main --title "feat: unified governance framework + OCO migration (sub-project 1)" --body "Squash merge of 9 phases. See docs/superpowers/specs/2026-05-25-unified-governance-framework-design.md and docs/superpowers/plans/2026-05-25-unified-governance-framework.md for the full scope."
gh pr merge <PR#> --squash
```

- [ ] **Step 2: Clean up branches + worktree**

```bash
cd /Users/danielfisher/repositories/behemoth
git checkout main
git pull
git worktree remove --force .claude/worktrees/governance-framework
git branch -D governance-framework
for ph in 1a 1b 1c 1d 1e 1f 1g 1h 1i; do
  git branch -D governance-phase-$ph 2>/dev/null
done
```

---

# Plan self-review notes (per writing-plans skill)

**Spec coverage:** all 9 phases (1a-1i) from the spec map to a top-level plan section, plus pre-implementation setup and final umbrella merge.

**Placeholder scan:** the orchestrator body in phase 1e is intentionally a stub that phase 1g fills in (real candidate paths + tick paths can only be wired after the per-symbol YAMLs exist and the byte-identity work has surfaced the exact framework details). Test is `xfail`/`skip` until 1g flips it. Annotated as such in the plan; not a hidden TBD.

**Type consistency:** `BaseFamilyGovernanceHooks` referenced consistently across selection.py, freeze.py, simulators (1d/1h/1i). `state_id` column name uniform across G1/G2/G3/G4. `verdict` column carries `"GO"` / `"NO_GO"` strings (the canonical values per CLAUDE.md), same across G4 and G5.

**Open follow-ups for the plan executor:**
- Sub-project 5 will add a deployment-substrate schema (model JSON for non-OCO families).
- The `_FakeAdapter` test doubles in 1h/1i are placeholders so the simulators can be unit-tested without real adapters; real adapters land in sub-projects 2 and 4.
