from scripts.fx_cluster import config


def test_pool_excludes_jpy_by_default():
    assert "USDJPY" in config.PAIRS
    assert "USDJPY" not in config.POOL_PAIRS
    assert set(config.POOL_PAIRS) == set(config.PAIRS) - {"USDJPY"}


def test_usd_signs_cover_all_pairs_and_are_unit():
    assert set(config.USD_SIGN) == set(config.PAIRS)
    assert all(v in (-1.0, 1.0) for v in config.USD_SIGN.values())
    # USD is the quote ccy in EURUSD/GBPUSD/AUDUSD -> USD up = pair down -> -1
    assert config.USD_SIGN["EURUSD"] == -1.0
    # USD is the base ccy in USDJPY/USDCHF/USDCAD -> USD up = pair up -> +1
    assert config.USD_SIGN["USDJPY"] == 1.0


def test_split_dates_ordered():
    assert config.TRAIN_START < config.TRAIN_END <= config.TEST_START < config.TEST_END
