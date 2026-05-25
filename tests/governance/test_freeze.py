import json

import pandas as pd

from src.behemoth.governance.families import get_family_adapter
from src.behemoth.governance.freeze import write_freeze_artifact


def test_freeze_writes_json_with_adapter_payload_and_symbol(tmp_path):
    adapter = get_family_adapter("oco_first_touch")
    qualified = pd.DataFrame(
        [
            {"state_id": "s1", "selected": True, "verdict": "GO"},
        ]
    )

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
    assert j["symbol"] == "EURUSD"
    assert j["qualified_states"] == [
        {"state_id": "s1", "selected": True, "verdict": "GO"}
    ]


def test_freeze_path_includes_symbol_and_family(tmp_path):
    adapter = get_family_adapter("oco_first_touch")
    qualified = pd.DataFrame([{"state_id": "s1", "selected": True, "verdict": "GO"}])

    path = write_freeze_artifact(
        out_dir=tmp_path,
        symbol="EURUSD",
        adapter=adapter,
        qualified_states=qualified,
        model_month="2026-05",
    )

    assert path.name == "EURUSD_oco_first_touch_governance_frozen.json"


def test_freeze_json_is_sorted_and_indented(tmp_path):
    adapter = get_family_adapter("oco_first_touch")
    qualified = pd.DataFrame([{"state_id": "s1", "selected": True, "verdict": "GO"}])

    path = write_freeze_artifact(
        out_dir=tmp_path,
        symbol="EURUSD",
        adapter=adapter,
        qualified_states=qualified,
        model_month="2026-05",
    )

    assert path.read_text().startswith('{\n  "family":')
