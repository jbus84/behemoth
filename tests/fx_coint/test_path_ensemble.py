# tests/fx_coint/test_path_ensemble.py
from scripts.fx_coint.path_ensemble import build_ensemble, tail_long_entries


def test_tail_long_entries_nonempty_and_long():
    ents = tail_long_entries("EURUSD", freq="2h", q=0.95)
    assert len(ents) > 30
    assert all(side == "long" for _, side, _ in ents)
    assert all(s > 0 for _, _, s in ents)


def test_offset_placebo_same_tod_excludes_signals():
    import pandas as pd

    from scripts.fx_coint.path_ensemble import offset_placebo_entries
    ents = tail_long_entries("EURUSD", freq="2h", q=0.95)
    excl = {b for b, _, _ in ents}
    plc = offset_placebo_entries("EURUSD", "2h", ents, min_off_days=3, max_off_days=60, seed=1)
    assert len(plc) > 0.8 * len(ents)            # most entries place-able
    assert not (excl & {b for b, _, _ in plc})   # none land on a real signal bar
    # same time-of-day preserved (offset is whole days)
    sig_h = pd.to_datetime(pd.Series([b for b, _, _ in ents])).dt.hour.value_counts(normalize=True)
    plc_h = pd.to_datetime(pd.Series([b for b, _, _ in plc])).dt.hour.value_counts(normalize=True)
    assert set(plc_h.index).issubset(set(sig_h.index))


def test_build_ensemble_columns_and_terminal_matches_baseline():
    ents = tail_long_entries("EURUSD", freq="2h", q=0.95)
    df = build_ensemble("EURUSD", ents, freq="2h", n_bars=1)
    assert {"terminal_bps", "mfe_sigma", "mae_sigma", "sigma_bps"}.issubset(df.columns)
    assert len(df) > 30
    # MFE >= 0 >= MAE by construction
    assert (df["mfe_sigma"] >= 0).all()
    assert (df["mae_sigma"] <= 0).all()


def test_reversion_entries_signed_and_causal():
    from scripts.fx_coint.path_ensemble import reversion_entries
    ents = reversion_entries("EURUSD", freq="1d", q=0.90, L=10)
    assert len(ents) > 20
    sides = {side for _, side, _ in ents}
    assert sides <= {"long", "short"}
    assert all(s > 0 for _, _, s in ents)
