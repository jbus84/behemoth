import numpy as np


class KalmanFilterReg:
    """
    Online Kalman Filter for Dynamic Regression: y = beta * x + noise
    Estimates beta_t (slope) iteratively.
    """

    def __init__(self, delta=1e-5, R=1e-3, Q=1e-5):
        """
        delta: ridge regularization for initial P
        R: measurement noise variance
        Q: process noise variance
        """
        self.R = R
        self.Q = Q
        self.beta = np.zeros(1)
        self.P = np.ones((1, 1)) * 1.0

    def update(self, x, y):
        """
        Update state with observation x (independent), y (dependent).
        Returns estimated beta and prediction error.
        """
        self.P = self.P + self.Q

        y_pred = self.beta[0] * x
        residual = y - y_pred

        S = x * self.P[0, 0] * x + self.R
        K = (self.P[0, 0] * x) / S

        self.beta[0] = self.beta[0] + K * residual
        self.P[0, 0] = (1 - K * x) * self.P[0, 0]

        return self.beta[0], residual


class KalmanFilterRegMulti:
    """
    Online Kalman Filter for Dynamic Regression (multi-hedge):
    y = beta' * x + noise
    where beta is a vector of slopes.
    """

    def __init__(self, k, delta=1e-5, R=1e-3, Q=1e-5):
        """
        k: number of hedge legs
        delta: ridge regularization for initial P
        R: measurement noise variance
        Q: process noise variance (scalar, applied to each beta)
        """
        self.R = R
        self.Q = Q
        self.k = int(k)
        self.beta = np.zeros(self.k)
        self.P = np.eye(self.k)

    def update(self, x, y):
        """
        x: vector of hedge inputs (shape: k,)
        y: scalar observation
        Returns beta vector and prediction residual.
        """
        x = np.asarray(x, dtype=float).reshape(-1)
        if x.shape[0] != self.k:
            raise ValueError(f"Expected x of shape ({self.k},), got {x.shape}")

        self.P = self.P + self.Q * np.eye(self.k)

        y_pred = float(np.dot(self.beta, x))
        residual = float(y - y_pred)

        S = float(x @ self.P @ x + self.R)
        if S <= 1e-12:
            return self.beta.copy(), residual

        K = (self.P @ x) / S
        self.beta = self.beta + K * residual
        self.P = (np.eye(self.k) - np.outer(K, x)) @ self.P

        return self.beta.copy(), residual


def compute_kalman_states(y, x, window=500, warmup=10):
    """
    Compute level and return Kalman states plus residual errors.
    """
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []
    errors = []

    for i in range(len(y)):
        if i < warmup:
            mu_y, mu_x = y[i], x[i]
        else:
            mu_y = np.mean(y[max(0, i - window) : i])
            mu_x = np.mean(x[max(0, i - window) : i])
        b, _ = kf.update(x[i] - mu_x, y[i] - mu_y)
        betas.append(b)
        errors.append((y[i] - mu_y) - b * (x[i] - mu_x))

    kf_ret = KalmanFilterReg(Q=1e-5, R=1e-3)
    ret_betas = np.zeros(len(y))
    if len(y) > 1:
        for i in range(1, len(y)):
            ry = y[i] - y[i - 1]
            rx = x[i] - x[i - 1]
            b_ret, _ = kf_ret.update(rx, ry)
            ret_betas[i] = b_ret
        ret_betas[0] = ret_betas[1]

    return np.array(betas), np.array(errors), ret_betas
