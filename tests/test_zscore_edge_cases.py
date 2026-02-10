import os
import sys

import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15
import build_meta_dataset_v3_m5 as m5


def test_compute_z_scores_zero_std_m5():
    errors = np.zeros(600)
    z = m5.compute_z_scores(errors, window=500)
    assert np.allclose(z, 0.0)


def test_compute_z_scores_zero_std_m15():
    errors = np.zeros(600)
    z = m15.compute_z_scores(errors, window=500)
    assert np.allclose(z, 0.0)
