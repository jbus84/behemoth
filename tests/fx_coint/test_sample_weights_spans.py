"""Tests for concurrency_spans and event_weights."""
import numpy as np

from scripts.fx_coint.sample_weights import concurrency_spans, event_weights


def test_concurrency_spans_counts_overlap():
    # two labels: [0,4] and [2,6] over a 10-bar timeline
    co = concurrency_spans(10, np.array([0, 2]), np.array([4, 6]))
    assert co[0] == 1            # only label 0
    assert co[3] == 2            # both overlap at bar 3
    assert co[5] == 1            # only label 1
    assert (co >= 1).all()       # floored at 1


def test_event_weights_higher_for_bigger_isolated_move():
    n = 200
    r = np.zeros(n)
    r[50] = 0.01                 # a big return inside event A's span only
    entry = np.array([48, 120])
    t1 = np.array([55, 130])     # event A spans the big bar; event B is flat
    w = event_weights(r, entry, t1)
    assert w[0] > w[1]           # A captured the move -> higher weight
    assert np.all(w >= 0)
