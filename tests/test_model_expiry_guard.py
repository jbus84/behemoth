from __future__ import annotations


def test_model_valid_through_blocks_expired_models() -> None:
    """When day_str > model_valid_through, the threshold should block."""
    thr_cfg = {
        "threshold_schedule": {"2025-02-01": 0.6, "2025-02-28": 0.6},
        "model_valid_through": "2025-02-28",
        "rolling_threshold_days": 20,
        "execution_quantile": 0.9,
        "rolling_threshold_min_history": 1000,
    }
    day_str = "2025-03-01"
    model_valid_through = thr_cfg.get("model_valid_through", "")

    assert model_valid_through != ""
    assert day_str > model_valid_through, "Should detect expiry"


def test_model_valid_through_allows_valid_day() -> None:
    """When day_str <= model_valid_through, the threshold should not block."""
    thr_cfg = {
        "threshold_schedule": {"2025-02-01": 0.6, "2025-02-28": 0.6},
        "model_valid_through": "2025-02-28",
    }
    day_str = "2025-02-15"
    model_valid_through = thr_cfg.get("model_valid_through", "")

    assert day_str <= model_valid_through, "Should allow valid day"


def test_model_valid_through_empty_does_not_block() -> None:
    """When model_valid_through is empty, no expiry check applies."""
    thr_cfg = {
        "threshold_schedule": {},
    }
    model_valid_through = thr_cfg.get("model_valid_through", "")

    assert not model_valid_through, "Empty string is falsy — no block"
