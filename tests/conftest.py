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

# Straddle feature/universe tests load a local tick-bar dataset via an absolute
# ``DATA_DIR`` hardcoded in the test module (``data/tick_bars`` on the operator's
# machine). That dataset is gitignored, so the tests run locally but have no data
# to load in CI. These modules are preserved working logic kept byte-identical to
# origin/main, so the skip is applied here rather than by editing the tests.
_STRADDLE_DATA_MODULES = {
    "tests.test_boostlss_xs_features",
    "tests.test_boostlss_xs_universe",
}


def pytest_collection_modifyitems(config, items):
    """Skip environment-dependent tests when their on-disk fixtures are absent.

    - ``requires_models`` tests skip when ``models/oco/*.cbm`` are absent. Local
      checkouts carry the model artifacts; CI does not (``models/`` is
      gitignored), so tests that load a real model binding skip there.
    - The straddle feature/universe tests skip when their hardcoded ``DATA_DIR``
      is not readable. The dataset is gitignored, so they run on the operator's
      machine and skip in CI rather than failing with ``KeyError`` / empty
      universes.
    """
    skip_models = None
    if not _MODELS_PRESENT:
        skip_models = pytest.mark.skip(
            reason="requires_models: no models/oco/*.cbm artifacts in this environment"
        )

    skip_straddle = None  # created lazily only when a data-dependent item is found

    for item in items:
        if skip_models is not None and "requires_models" in item.keywords:
            item.add_marker(skip_models)
        if item.module.__name__ in _STRADDLE_DATA_MODULES:
            data_dir = getattr(item.module, "DATA_DIR", None)
            if data_dir is None or not pathlib.Path(data_dir).exists():
                if skip_straddle is None:
                    skip_straddle = pytest.mark.skip(
                        reason="requires local tick_bars dataset (gitignored; absent in CI)"
                    )
                item.add_marker(skip_straddle)
