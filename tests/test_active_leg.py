from behemoth.core.active_leg import select_active_leg


def test_select_active_leg_y():
    assert select_active_leg(0.97) == "Y"


def test_select_active_leg_x():
    assert select_active_leg(1.03) == "X"


def test_select_active_leg_neutral():
    assert select_active_leg(1.0) is None
