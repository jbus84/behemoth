import pytest

from src.behemoth.governance.errors import UnknownFamilyError
from src.behemoth.governance.families import (
    FAMILY_GOVERNANCE_REGISTRY,
    get_family_adapter,
)


def test_registry_is_a_dict_keyed_by_family_name():
    assert isinstance(FAMILY_GOVERNANCE_REGISTRY, dict)


def test_get_family_adapter_unknown_raises():
    with pytest.raises(UnknownFamilyError):
        get_family_adapter("not_a_family")


def test_get_family_adapter_returns_hook_instance_for_known():
    adapter = get_family_adapter("oco_first_touch")
    assert adapter.config.name == "oco_first_touch"
