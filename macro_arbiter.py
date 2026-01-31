import polars as pl
import numpy as np
import os

class MacroArbiter:
    """
    Unified Arbiter for the Macro-Lag Toolkit v1.0.
    Manages signals for Paradox Sniper, Nasdaq Slingshot, and Surgical Sentinel.
    """
    
    def __init__(self, spread=1.5, n_anchors=8):
        self.spread = spread
        self.n_anchors = n_anchors
        self.nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        self.anchors = [n for n in self.nodes if n != 'NSXUSD']

    def calculate_signals(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Input: 1m OHLC Parquet with 1m returns and 30m volatility.
        Output: DataFrame with added signal columns.
        """
        # 1. Base Consensus & Energy
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in self.anchors]).alias("consensus_up"),
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in self.anchors]).alias("consensus_down"),
            pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in self.anchors]).alias("macro_energy"),
            pl.col("timestamp").dt.hour().alias("hour_utc"),
            pl.col("NSXUSD_vol_30m").alias("vol")
        ])

        # 2. Strategy Logic Configuration
        CONSENSUS_GO = 7
        NSX_QUIET = 0.2 / 10000
        SLINGSHOT_DIV = 1.0 / 10000
        PARADOX_ENERGY = 2.0 / 10000
        PARADOX_STALL = 0.1 / 10000
        ROGUE_TENSION = 25.0 / 10000
        ZERO_TENSION = 10.0 / 10000
        ZERO_STALL = 1e-9
        MOMENTUM_THR = 25.0 / 10000
        SILENCE_QUIET = 1.0 / 10000
        SILENCE_BREAKOUT = 2.0 / 10000

        # 1. Feature Engineering: London Trend (4h / 240 mins) & Rolling Energy
        df = df.with_columns([
            (pl.col("NSXUSD_mid").log() - pl.col("NSXUSD_mid").shift(240).log()).alias("london_trend"),
            pl.col("macro_energy").rolling_max(window_size=30).alias("max_energy_30m")
        ])

        # 3. Apply Strategies
        df = df.with_columns([
            # [A] Paradox Sniper
            (
                (pl.col("consensus_up") >= CONSENSUS_GO) & 
                (pl.col("macro_energy") > PARADOX_ENERGY) & 
                (pl.col("NSXUSD_ret_1m").abs() < PARADOX_STALL)
            ).alias("sig_paradox_long"),
            (
                (pl.col("consensus_down") >= CONSENSUS_GO) & 
                (pl.col("macro_energy") > PARADOX_ENERGY) & 
                (pl.col("NSXUSD_ret_1m").abs() < PARADOX_STALL)
            ).alias("sig_paradox_short"),

            # [B] Nasdaq Slingshot
            (
                pl.col("hour_utc").is_between(12, 20) &
                (pl.col("consensus_up") >= CONSENSUS_GO) & 
                (pl.col("NSXUSD_ret_1m") < -SLINGSHOT_DIV)
            ).alias("sig_slingshot_long"),
            (
                pl.col("hour_utc").is_between(12, 20) &
                (pl.col("consensus_down") >= CONSENSUS_GO) & 
                (pl.col("NSXUSD_ret_1m") > SLINGSHOT_DIV)
            ).alias("sig_slingshot_short"),

            # [C] Surgical Sentinel
            (
                pl.col("hour_utc").is_between(14, 19) &
                ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0)) &
                (pl.col("consensus_up") >= CONSENSUS_GO) & 
                (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)
            ).alias("sig_sentinel_long"),
            (
                pl.col("hour_utc").is_between(14, 19) &
                ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0)) &
                (pl.col("consensus_down") >= CONSENSUS_GO) & 
                (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)
            ).alias("sig_sentinel_short"),

            # [D] Double-Negative Rogue
            (
                (pl.col("consensus_up") >= CONSENSUS_GO) & 
                ((pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")) < -ROGUE_TENSION)
            ).alias("sig_rogue_long"),
            (
                (pl.col("consensus_down") >= CONSENSUS_GO) & 
                ((pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")) > ROGUE_TENSION)
            ).alias("sig_rogue_short"),

            # [E] Absolute Zero Tension
            (
                (pl.col("consensus_up") >= CONSENSUS_GO) & 
                ((pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")) < -ZERO_TENSION) &
                (pl.col("NSXUSD_ret_1m").abs() < ZERO_STALL)
            ).alias("sig_zero_long"),
            (
                (pl.col("consensus_down") >= CONSENSUS_GO) & 
                ((pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")) > ZERO_TENSION) & 
                (pl.col("NSXUSD_ret_1m").abs() < ZERO_STALL)
            ).alias("sig_zero_short"),

            # [F] Session Momentum Anchor
            (
                (pl.col("timestamp").dt.hour() == 13) & 
                (pl.col("timestamp").dt.minute() == 30) &
                (pl.col("london_trend") > MOMENTUM_THR)
            ).alias("sig_anchor_long"),
            (
                (pl.col("timestamp").dt.hour() == 13) & 
                (pl.col("timestamp").dt.minute() == 30) &
                (pl.col("london_trend") < -MOMENTUM_THR)
            ).alias("sig_anchor_short"),

            # [G] The Silence Trap (Fade Breakout)
            # Logic: Shift(1) Max Energy < 1.0 AND Current Energy > 2.0
            # Direction: Fade the consensus (Short if Consensus UP, Long if Consensus DOWN)
            (
                (pl.col("max_energy_30m").shift(1) < SILENCE_QUIET) &
                (pl.col("macro_energy") > SILENCE_BREAKOUT) &
                (pl.col("consensus_down") >= CONSENSUS_GO) # Consensus Down -> Fakeout -> Buy
            ).alias("sig_silence_long"),
            (
                (pl.col("max_energy_30m").shift(1) < SILENCE_QUIET) &
                (pl.col("macro_energy") > SILENCE_BREAKOUT) &
                (pl.col("consensus_up") >= CONSENSUS_GO) # Consensus Up -> Fakeout -> Sell
            ).alias("sig_silence_short")
        ])

        # 4. Arbitration: Combined Signal (Priority: Paradox > Silence > Slingshot > Sentinel)
        df = df.with_columns(
            pl.when(pl.col("sig_paradox_long")).then(pl.lit("PARADOX_LONG"))
              .when(pl.col("sig_paradox_short")).then(pl.lit("PARADOX_SHORT"))
              .when(pl.col("sig_zero_long")).then(pl.lit("ZERO_TENSION_LONG"))
              .when(pl.col("sig_zero_short")).then(pl.lit("ZERO_TENSION_SHORT"))
              .when(pl.col("sig_silence_long")).then(pl.lit("SILENCE_TRAP_LONG"))  # New Priority
              .when(pl.col("sig_silence_short")).then(pl.lit("SILENCE_TRAP_SHORT")) # New Priority
              .when(pl.col("sig_anchor_long")).then(pl.lit("MOMENTUM_ANCHOR_LONG"))
              .when(pl.col("sig_anchor_short")).then(pl.lit("MOMENTUM_ANCHOR_SHORT"))
              .when(pl.col("sig_rogue_long")).then(pl.lit("ROGUE_LONG"))
              .when(pl.col("sig_rogue_short")).then(pl.lit("ROGUE_SHORT"))
              .when(pl.col("sig_slingshot_long")).then(pl.lit("SLINGSHOT_LONG"))
              .when(pl.col("sig_slingshot_short")).then(pl.lit("SLINGSHOT_SHORT"))
              .when(pl.col("sig_sentinel_long")).then(pl.lit("SENTINEL_LONG"))
              .when(pl.col("sig_sentinel_short")).then(pl.lit("SENTINEL_SHORT"))
              .otherwise(None).alias("combined_signal")
        )

        return df

    def run_backtest(self, file_path):
        if not os.path.exists(file_path):
            print(f"File {file_path} not found.")
            return

        df = pl.read_parquet(file_path)
        df = self.calculate_signals(df)

        # Dynamic Targets (15m for high-freq, 120m for Anchor)
        df = df.with_columns([
            (pl.col("NSXUSD_mid").shift(-15).log() - pl.col("NSXUSD_mid").log()).alias("target_15m"),
            (pl.col("NSXUSD_mid").shift(-120).log() - pl.col("NSXUSD_mid").log()).alias("target_120m")
        ])

        # Calculate PnL for signals
        df = df.with_columns(
            pl.when(pl.col("combined_signal").is_null()).then(0)
            .when(pl.col("combined_signal").str.contains("LONG"))
            .then(
                pl.when(pl.col("combined_signal").str.contains("ANCHOR"))
                .then(pl.col("target_120m") * 10000 - self.spread)
                .otherwise(pl.col("target_15m") * 10000 - self.spread)
            )
            .when(pl.col("combined_signal").str.contains("SHORT"))
            .then(
                pl.when(pl.col("combined_signal").str.contains("ANCHOR"))
                .then(-pl.col("target_120m") * 10000 - self.spread)
                .otherwise(-pl.col("target_15m") * 10000 - self.spread)
            )
            .otherwise(0).alias("pnl_net")
        )

        results = df.filter(pl.col("combined_signal").is_not_null())
        
        print(f"\n>>> ARBITER BACKTEST RESULTS: {file_path} <<<")
        if len(results) > 0:
            print(f"  Total Trades: {len(results)}")
            print(f"  Win Rate:     {(results['pnl_net'] > 0).mean()*100:.2f}%")
            print(f"  Avg PnL:      {results['pnl_net'].mean():.3f} bps")
            print(f"  Total PnL:    {results['pnl_net'].sum():.2f} bps")
            
            # Breakdown by signal type
            breakdown = results.group_by("combined_signal").agg([
                pl.len().alias("count"),
                pl.col("pnl_net").mean().alias("avg_pnl")
            ]).sort("combined_signal")
            print("\n  Signal Breakdown:")
            print(breakdown)
        else:
            print("  No signals detected.")

if __name__ == "__main__":
    import sys
    arbiter = MacroArbiter()
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["graph_dataset_1m_2025.parquet"]
    for p in paths:
        arbiter.run_backtest(p)
