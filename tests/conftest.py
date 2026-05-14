import os
import pathlib
import sys

import pytest

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "pipelines"))

# Tests should not bind to the shared runtime DuckDB file unless they opt in.
os.environ.setdefault("BEHEMOTH_STATE_DB", "")


_MODELS_PRESENT = bool(list(pathlib.Path(ROOT, "models", "oco").glob("*_model_*.cbm")))


def pytest_collection_modifyitems(config, items):
    """Skip tests marked ``requires_models`` when models/oco/*.cbm are absent.

    Local checkouts typically carry the model artifacts on disk and run the
    full suite. CI does not (``models/`` is gitignored), so tests that load
    a real model binding skip automatically there.
    """
    if _MODELS_PRESENT:
        return
    skip_marker = pytest.mark.skip(
        reason="requires_models: no models/oco/*.cbm artifacts in this environment"
    )
    for item in items:
        if "requires_models" in item.keywords:
            item.add_marker(skip_marker)
