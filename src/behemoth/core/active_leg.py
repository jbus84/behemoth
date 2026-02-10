def select_active_leg(beta, low=0.98, high=1.02):
    """
    Select which leg to trade based on beta thresholds.
    Returns "Y", "X", or None for neutral zone.
    """
    if beta < low:
        return "Y"
    if beta > high:
        return "X"
    return None
