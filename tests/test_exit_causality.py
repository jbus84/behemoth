import numpy as np

from behemoth.core.events import simulate_trade


def test_exit_ignores_future_bars_after_exit():
    # Exit should trigger at idx=1 on z-cross; future bars should not alter duration/outcome.
    y = np.array([1.0, 1.01, 1.02, 1.50])
    x = np.array([1.0, 1.0, 1.0, 1.0])
    z = np.array([2.0, -0.1, 10.0, -10.0])

    pnl1, dur1, out1 = simulate_trade(0, 1, "MOM", y, x, z, "Y", stop=3.5)

    # Append extreme future movement; exit should remain the same.
    y2 = np.array([1.0, 1.01, 1.02, 5.0, 10.0])
    z2 = np.array([2.0, -0.1, 10.0, -10.0, 10.0])
    pnl2, dur2, out2 = simulate_trade(
        0,
        1,
        "MOM",
        y2,
        x=np.array([1.0, 1.0, 1.0, 1.0, 1.0]),
        z_scores=z2,
        active_asset="Y",
        stop=3.5,
    )

    assert dur1 == dur2
    assert out1 == out2
    assert pnl1 == pnl2
