import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from services.api import predict, validation
from services.api.main import app


def test_predictions_alignment(monkeypatch, tmp_path):
    # mock series to produce deterministic events
    ts = pd.Series([0, 1, 2, 3], dtype="int64").to_numpy()
    y = pd.Series([1.0, 1.01, 1.02, 1.03]).to_numpy()
    x = pd.Series([1.0, 1.0, 1.0, 1.0]).to_numpy()

    def fake_load_pair_series(bar, pair):
        return ts, y, x

    def fake_compute_kalman_states(y_in, x_in):
        n = len(y_in)
        return np.ones(n) * 1.1, np.zeros(n), np.zeros(n)

    def fake_compute_z_scores(errors):
        return np.array([0.0, 2.0, -0.1, 4.0])

    monkeypatch.setattr(predict, "load_pair_series", fake_load_pair_series)
    monkeypatch.setattr(predict, "compute_kalman_states", fake_compute_kalman_states)
    monkeypatch.setattr(predict, "compute_z_scores", fake_compute_z_scores)

    # create pipeline CSV using the same generator
    events = predict.generate_mom_events_for_pair("m5", "EUR/GBP")
    df = pd.DataFrame(
        {
            "pair": [e["pair"] for e in events],
            "timestamp": [e["entry_ts"] for e in events],
            "duration_bars": [e["duration_bars"] for e in events],
            "pnl_bps": [e["pnl_bps"] for e in events],
        }
    )
    path = tmp_path / "events.csv"
    df.to_csv(path, index=False)
    validation.PIPELINE_PATHS["m5"] = str(path)

    client = TestClient(app)
    resp = client.get("/validation/predictions/m5/EUR%2FGBP")
    assert resp.status_code == 200
    data = resp.json()
    assert data["match_rate"] == 1.0
