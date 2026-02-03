#!/usr/bin/env python3
"""
Meta Model Inference Engine
Loads trained CatBoost model and generates signals from OHLC data.
"""

import polars as pl
import pandas as pd
import numpy as np
import os
import sys
from catboost import CatBoostRegressor

# Add scripts to path for Kalman
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

MODEL_PATH = "models/meta_model_h1/catboost_h1_reg.cbm"

FEATURE_NAMES = [
    'strategy_type', 'active_leg', 'side', # Categorical
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]

CAT_INDICES = [0, 1, 2] # strategy_type, active_leg, side are first 3 in ALL_FEATURES if constructed carefully
# BUT CatBoost stores feature names. We should pass pandas DataFrame with named columns.

class MetaModelInference:
    def __init__(self, model_path=MODEL_PATH, load_model=True):
        self.model = None
        if load_model:
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model not found at {model_path}")

            self.model = CatBoostRegressor()
            self.model.load_model(model_path)
            print("Meta Model loaded successfully.")
        
    def _compute_kalman(self, y, x):
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas = np.zeros(len(y))
        errors = np.zeros(len(y))

        # Match training centering:
        # - For i < 10: use current value (no real window yet)
        # - For i >= 10: mean of last 500 bars excluding current (i-500:i)
        for i in range(len(y)):
            if i < 10:
                my, mx = y[i], x[i]
            else:
                start = max(0, i - 500)
                my = np.mean(y[start:i])
                mx = np.mean(x[start:i])

            b, resid = kf.update(x[i] - mx, y[i] - my)
            betas[i] = b
            errors[i] = (y[i] - my) - b * (x[i] - mx)
            
        return betas, errors

    def _compute_features(self, df, betas, errors, z_scores):
        # Expects df with timestamp, close_X, close_Y
        # Returns DataFrame with meta features for the TAIL
        
        # We process the whole dataframe vectorised, then slice the end.
        df = df.with_columns([
            pl.Series(betas).alias("beta"),
            pl.Series(errors).alias("spread_error"),
            pl.Series(z_scores).alias("z_score")
        ])
        
        # Convert to Pandas for Rolling Features (easier/consistent with training)
        pdf = df.to_pandas()
        pdf['log_y'] = np.log(pdf['close_Y'])
        pdf['log_x'] = np.log(pdf['close_X'])
        
        # 1. Z-Stats
        pdf['z_entry'] = pdf['z_score'].round(2)
        pdf['z_velocity'] = (pdf['z_score'] - pdf['z_score'].shift(5)).round(2)
        # Match training: use windows ending at i-1 (exclude current)
        pdf['spread_std'] = (pdf['spread_error'].shift(1).rolling(500).std(ddof=0) * 10000).round(2)
        pdf['beta_stability'] = pdf['beta'].shift(1).rolling(100).std(ddof=0).round(4)
        
        # 2. Market Regime
        # Vol Ratio (Diff log prices)
        dy = pdf['log_y'].diff()
        dx = pdf['log_x'].diff()
        vol_y = dy.shift(1).rolling(500).std(ddof=0)
        vol_x = dx.shift(1).rolling(500).std(ddof=0)
        pdf['vol_ratio'] = (vol_y / vol_x).replace([np.inf, -np.inf], 1.0).fillna(1.0).round(3)
        
        # Correlation
        pdf['correlation_500'] = pdf['log_y'].shift(1).rolling(500).corr(pdf['log_x'].shift(1)).fillna(0.0).round(3)
        
        # Trend Strength (Slope/Std of spread 100)
        # Training uses: spread = y[i-100:i] - beta[i] * x[i-100:i]
        # trend_strength = slope(spread) / std(spread)
        # For inference, compute this for the last bar only to avoid heavy rolling.
        
        # 3. Time
        # pdf['hour'] = pd.to_datetime(pdf['timestamp']).dt.hour # Timestamp is already datetime?
        # Timestamp might be int ns.
        if pdf['timestamp'].dtype == 'int64':
             pdf['dt'] = pd.to_datetime(pdf['timestamp'], unit='ns')
        else:
             pdf['dt'] = pd.to_datetime(pdf['timestamp'])
        
        pdf['hour'] = pdf['dt'].dt.hour
        pdf['day_of_week'] = pdf['dt'].dt.dayofweek
        
        # 4. Returns
        # H1 Model used 4-bar lookback for "4h" returns? Or 16?
        # Training script: `lookback = min(i, 16)`.
        # Training uses lookback = min(i, 16), so for mature series this is 16 bars.
        pdf['ret_X_4h'] = ((pdf['log_x'] - pdf['log_x'].shift(16)) * 10000).round(2)
        pdf['ret_Y_4h'] = ((pdf['log_y'] - pdf['log_y'].shift(16)) * 10000).round(2)
        
        # 5. ATR (Entry Volatility)
        # Training: std of last 50 diffs
        pdf['entry_atr'] = (dy.shift(1).rolling(50).std(ddof=0) * 10000).round(2)
        
        # 6. Vol Regime
        long_vol = dy.shift(1).rolling(500).std(ddof=0)
        short_vol = dy.shift(1).rolling(50).std(ddof=0)
        pdf['vol_regime'] = (short_vol / long_vol).fillna(1.0).round(2)
        
        # 7. Trend Strength (default 0.0, last bar set below)
        pdf['trend_strength'] = 0.0

        # 8. ATR Ratio (default 1.0, last bar set below)
        pdf['atr_ratio'] = 1.0

        # Fill NA
        pdf = pdf.fillna(0)

        # --- Compute last-bar-only features to match training ---
        # Trend Strength
        n = len(pdf)
        if n >= 101:
            b = pdf['beta'].iloc[-1]
            y_win = pdf['log_y'].to_numpy()[-101:-1]
            x_win = pdf['log_x'].to_numpy()[-101:-1]
            spread = y_win - b * x_win
            slope = np.polyfit(np.arange(100), spread, 1)[0]
            denom = np.std(spread) + 1e-8
            trend = slope / denom
            pdf.loc[pdf.index[-1], 'trend_strength'] = round(trend, 3)
        else:
            pdf.loc[pdf.index[-1], 'trend_strength'] = 0.0

        # Vol Ratio (match build_meta_dataset_v3_h1.py)
        if n >= 501:
            y_arr = pdf['log_y'].to_numpy()
            x_arr = pdf['log_x'].to_numpy()
            y_hist = y_arr[-501:-1]
            x_hist = x_arr[-501:-1]
            vol_y = np.std(np.diff(y_hist))
            vol_x = np.std(np.diff(x_hist))
            vol_ratio = vol_y / vol_x if vol_x > 0 else 1.0
            pdf.loc[pdf.index[-1], 'vol_ratio'] = round(vol_ratio, 3)

        # ATR Ratio (match build_meta_dataset_v3_h1.py)
        if n >= 101:
            y_arr = pdf['log_y'].to_numpy()
            x_arr = pdf['log_x'].to_numpy()
            start = n - 101
            end = n - 1
            atr_y = np.mean([np.max(y_arr[j:j+4]) - np.min(y_arr[j:j+4]) for j in range(start, end, 4)])
            atr_x = np.mean([np.max(x_arr[j:j+4]) - np.min(x_arr[j:j+4]) for j in range(start, end, 4)])
            atr_ratio = atr_y / atr_x if atr_x > 0 else 1.0
            pdf.loc[pdf.index[-1], 'atr_ratio'] = round(atr_ratio, 3)
        else:
            pdf.loc[pdf.index[-1], 'atr_ratio'] = 1.0

        # Entry ATR (match build_meta_dataset_v3_h1.py)
        if n >= 51:
            y_arr = pdf['log_y'].to_numpy()
            recent_returns = np.diff(y_arr[-51:-1])
            entry_atr = np.std(recent_returns) * 10000
            pdf.loc[pdf.index[-1], 'entry_atr'] = round(entry_atr, 2)

        # Vol Regime (match build_meta_dataset_v3_h1.py)
        if n >= 501:
            y_arr = pdf['log_y'].to_numpy()
            short_vol = np.std(np.diff(y_arr[-51:-1]))
            long_vol = np.std(np.diff(y_arr[-501:-1]))
            vol_regime = short_vol / long_vol if long_vol > 0 else 1.0
            pdf.loc[pdf.index[-1], 'vol_regime'] = round(vol_regime, 2)
        
        return pdf

    def predict_next(self, pair_name, df_x, df_y):
        """
        Generate signal for the LATEST bar.
        Returns dict with Decision and Metrics.
        """
        if self.model is None:
            raise RuntimeError("Model is not loaded. Initialize with load_model=True for predictions.")
        # Join
        df = df_x.rename({'close': 'close_X'}).join(
            df_y.rename({'close': 'close_Y'}), on='timestamp', how='inner'
        ).sort('timestamp')
        
        if len(df) < 505:
            return {'action': 'WAIT', 'reason': 'Not enough data'}
            
        y = np.log(df["close_Y"].to_numpy())
        x = np.log(df["close_X"].to_numpy())
        
        betas, errors = self._compute_kalman(y, x)
        
        # Z-Scores
        s_err = pd.Series(errors)
        roll = s_err.rolling(500)
        mus = roll.mean().shift(1).fillna(0).values
        stds = roll.std(ddof=0).shift(1).fillna(1).values
        z_scores = np.zeros_like(errors)
        mask = stds > 1e-8
        z_scores[mask] = (errors[mask] - mus[mask]) / stds[mask]
        
        # Features
        pdf = self._compute_features(df, betas, errors, z_scores)
        last_row = pdf.iloc[-1]
        
        z = last_row['z_entry']
        beta = last_row['beta']
        
        # Whip/Tank Filter
        if 0.98 <= beta <= 1.02:
            return {'action': 'WAIT', 'reason': 'Unstable Beta (1.0)', 'z': z}
            
        active_leg = 'Y' if beta < 0.98 else 'X'
        
        # Logic
        signals = []
        for strat in ['MOM', 'REV']:
            # Construct Input Row
            # Determine Side
            if strat == 'MOM':
                # Long logic: Z < 0? No, wait.
                # If Z > 1.5 -> Long MOM.
                # If Z < -1.5 -> Short MOM.
                if z > 1.5: side = 'LONG'
                elif z < -1.5: side = 'SHORT'
                else: side = 'NONE'
            else: # REV
                # Fade logic
                if z > 1.5: side = 'SHORT'
                elif z < -1.5: side = 'LONG'
                else: side = 'NONE'
            
            if side == 'NONE': continue
            
            # Create feature vector
            feat_vec = pd.DataFrame([last_row])
            feat_vec['strategy_type'] = strat
            feat_vec['active_leg'] = active_leg
            feat_vec['side'] = side
            
            # Select columns to match training
            X_pred = feat_vec[FEATURE_NAMES]
            
            pred_pnl = self.model.predict(X_pred)[0]
            
            if pred_pnl > 20.0:
                signals.append({
                    'strategy': strat,
                    'side': side,
                    'active_leg': active_leg,
                    'pred_pnl': round(pred_pnl, 2),
                    'z': z
                })
        
        if not signals:
            return {'action': 'WAIT', 'reason': 'Low Pred PnL', 'z': z}
            
        # Select best signal
        best_sig = max(signals, key=lambda s: s['pred_pnl'])
        return {'action': 'TRADE', 'signal': best_sig}

# Test block
if __name__ == "__main__":
    inf = MetaModelInference()
    
    # Load sample H1 data
    print("Loading sample H1 data...")
    try:
        p_x = "data/global_1h/BCOUSD_1h.parquet"
        p_y = "data/global_1h/XAUUSD_1h.parquet"
        
        if os.path.exists(p_x) and os.path.exists(p_y):
            df_x = pl.read_parquet(p_x).rename({'close_BCOUSD': 'close'})
            df_y = pl.read_parquet(p_y).rename({'close_XAUUSD': 'close'})
            
            print("Predicting Gold/Oil...")
            res = inf.predict_next("Gold/Oil", df_x, df_y)
            print("Result:", res)
    except Exception as e:
        print(e)
