from __future__ import annotations

from scripts.era_tick.micro_price import KalmanMicroPrice


def test_first_update_initialises_to_measurement():
    kf = KalmanMicroPrice()
    st = kf.update(1.2345, dt=0.0)
    assert st.mid_hat == 1.2345
    assert st.drift_hat == 0.0
    assert not_warm_then_warm(kf)


def not_warm_then_warm(kf: KalmanMicroPrice) -> bool:
    return kf.warm


def test_tracks_a_ramp_with_positive_drift():
    kf = KalmanMicroPrice(process_var=1e-8, meas_var=1e-10)
    mid = 1.10
    last = None
    for _ in range(300):
        mid += 1e-4  # one pip per tick, dt=1s -> drift ~ 1e-4 / s
        last = kf.update(mid, dt=1.0)
    assert last is not None
    assert last.drift_hat > 0.0
    # filtered price stays within a few pips of the (noiseless) truth
    assert abs(last.mid_hat - mid) < 5e-4


def test_step_produces_signed_residual():
    kf = KalmanMicroPrice(process_var=1e-10, meas_var=1e-10)
    for _ in range(100):
        kf.update(1.10, dt=1.0)
    jumped = kf.update(1.10 + 20e-4, dt=1.0)  # +20 pip shock
    assert jumped.residual > 0.0
    assert jumped.residual_z() > 0.0
