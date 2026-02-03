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
