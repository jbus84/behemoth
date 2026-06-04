from scripts.era_scalp.cost_aware_score import _sidak_z, fair_node_value


def test_sidak_no_correction_when_single_cell():
    assert abs(_sidak_z(1.645, 1) - 1.645) < 1e-9


def test_sidak_more_conservative_with_more_cells():
    assert _sidak_z(1.645, 15) > _sidak_z(1.645, 2) > _sidak_z(1.645, 1)


def test_fair_value_single_cell_matches_plain_lb():
    assert abs(fair_node_value([(2.0, 0.5)], m=1, z_base=1.645) - (2.0 - 1.645 * 0.5)) < 1e-9


def test_fair_value_penalises_multiplicity():
    cell = [(2.0, 0.5)]
    assert fair_node_value(cell, m=15, z_base=1.645) < fair_node_value(cell, m=1, z_base=1.645)


def test_fair_value_penalises_high_variance_spike():
    assert fair_node_value([(3.0, 0.2)], m=15) > fair_node_value([(3.0, 2.0)], m=15)


def test_fair_value_rewards_robust_region_over_single_spike():
    spike = fair_node_value([(5.0, 3.0), (0.1, 0.3), (0.0, 0.3)], m=15)
    robust = fair_node_value([(2.0, 0.4), (1.8, 0.4), (1.9, 0.5)], m=15)
    assert robust > spike


def test_fair_value_empty_is_nan():
    import math
    assert math.isnan(fair_node_value([], m=15))
