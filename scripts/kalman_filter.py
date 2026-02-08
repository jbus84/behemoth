import numpy as np

class KalmanFilterReg:
    """
    Online Kalman Filter for Dynamic Regression: y = beta * x + noise
    Estimates beta_t (slope) iteratively.
    
    VERIFIED TUNING (4-Hour Bars):
    - Q = 1e-5 (Optimal per Diagnostic Monte Carlo).
    - R = 1e-3 (Optimal).
    - Effective Lookback: 2 Bars (8 Hours). Fast adaptation to regime shifts.
    """
    def __init__(self, delta=1e-5, R=1e-3, Q=1e-5):
        """
        delta: ridge regularization for initial P
        R: measurement noise variance (volatility of spread). Set to 1e-3.
        Q: process noise variance (volatility of beta). Set to 1e-5.
        """
        self.R = R # Measurement Noise (Scalar)
        self.Q = Q # Process Noise (Scalar) for Beta
        
        # State: Beta (Slope)
        self.beta = np.zeros(1) 
        
        # Error Covariance Matrix (1x1 for single beta)
        self.P = np.ones((1, 1)) * 1.0 
        
    def update(self, x, y):
        """
        Update state with observation x (independent), y (dependent).
        Returns estimated beta and prediction error.
        """
        # 1. Prediction (Time Update)
        # Beta is assumed random walk: beta_t = beta_{t-1} + noise
        # P_t|t-1 = P_{t-1|t-1} + Q
        self.P = self.P + self.Q
        
        # 2. Measurement Update
        # Res = y - H*beta (where H=x)
        y_pred = self.beta[0] * x
        residual = y - y_pred # spread
        
        # Kalman Gain K = P * H' / (H * P * H' + R)
        S = x * self.P[0,0] * x + self.R # Innovation Covariance (Scalar)
        K = (self.P[0,0] * x) / S 
        
        # New Beta = Old Beta + K * residual
        self.beta[0] = self.beta[0] + K * residual
        
        # New P = (I - K*H) * P
        self.P[0,0] = (1 - K * x) * self.P[0,0]
        
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

        # Prediction step
        self.P = self.P + self.Q * np.eye(self.k)

        # Measurement update
        y_pred = float(np.dot(self.beta, x))
        residual = float(y - y_pred)

        S = float(x @ self.P @ x + self.R)
        if S <= 1e-12:
            return self.beta.copy(), residual

        K = (self.P @ x) / S  # shape: (k,)
        self.beta = self.beta + K * residual
        self.P = (np.eye(self.k) - np.outer(K, x)) @ self.P

        return self.beta.copy(), residual
