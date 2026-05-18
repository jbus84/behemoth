from __future__ import annotations

import pytest

from scripts.mining_family import FAMILY_REGISTRY, MiningFamily, resolve_families


def test_resolve_families_maps_legacy_library_type():
    assert resolve_families("oco") == ["oco_first_touch"]
    assert resolve_families("directional") == ["directional"]
    assert resolve_families("separate") == ["oco_first_touch", "directional"]


def test_resolve_families_rejects_unknown():
    with pytest.raises(ValueError, match="unknown"):
        resolve_families("nonsense")


def test_registry_entries_satisfy_protocol():
    assert not FAMILY_REGISTRY, "Registry is empty until concrete families are added in later tasks"
    for name, fam in FAMILY_REGISTRY.items():
        assert isinstance(fam, MiningFamily)
        assert fam.name == name
        for method in ("param_grid", "entry_indices", "measure_gross",
                       "candidate_metadata"):
            assert callable(getattr(fam, method))
