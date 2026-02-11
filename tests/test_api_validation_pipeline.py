import pandas as pd
from fastapi.testclient import TestClient

from services.api import validation
from services.api.main import app


def test_pipeline_validation_endpoint(tmp_path, monkeypatch):
    sample = pd.DataFrame({"pnl_bps": [1.0, -2.0, 3.0]})
    path = tmp_path / "events.csv"
    sample.to_csv(path, index=False)

    monkeypatch.setitem(validation.PIPELINE_PATHS, "m5", str(path))

    client = TestClient(app)
    resp = client.get("/validation/pipeline/m5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] == 3
    assert abs(data["mean_pnl"] - (1.0 - 2.0 + 3.0) / 3) < 1e-6
    assert abs(data["total_pnl"] - 2.0) < 1e-6
