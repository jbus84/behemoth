import polars as pl
import os
import glob
from datetime import timedelta

# Config
TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUTPUT_DIR = "/Users/danielfisher/repositories/behemoth/data/pairs"

def process_asset(symbol, interval="4h"):
    print(f"Processing {symbol}...")
    files = sorted(glob.glob(os.path.join(TICK_ROOT, symbol, "*_ticks.parquet")))
    if not files:
        print(f"No files found for {symbol}")
        return None

    # Lazy scan might be better for memory, but eager is fine for 4H agg
    # Process file by file to 1m, then concat, then 4h
    dfs = []
    for f in files:
        # Load columns: timestamp, bid
        # Use Bid for consistency
        try:
            q = pl.scan_parquet(f).select(["timestamp", "bid"])

            # Resample to 1m first (drastically reduces size)
            # Group dynamic needs sorted
            # We assume files are sorted time-wise.

            q_1m = q.sort("timestamp").group_by_dynamic("timestamp", every="1m").agg([
                pl.col("bid").last().alias("close")
            ])

            dfs.append(q_1m.collect())
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if not dfs:
        return None

    full_1m = pl.concat(dfs).sort("timestamp")

    # Resample to Target Interval (4H)
    # Using '4h'
    df_resampled = full_1m.group_by_dynamic("timestamp", every=interval).agg([
        pl.col("close").last().alias(f"close_{symbol}")
    ])

    return df_resampled

def build_pairs():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. Indices (NSX vs SPX)
    print("--- Building Index Pair (NSX, SPX) ---")
    df_nsx = process_asset("NSXUSD", "4h")
    df_spx = process_asset("SPXUSD", "4h")

    if df_nsx is not None and df_spx is not None:
        # Align (Inner Join)
        print("Aligning Indices...")
        df_indices = df_nsx.join(df_spx, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_indices_4h.parquet")
        df_indices.write_parquet(out_path)
        print(f"Saved Indices: {len(df_indices)} rows to {out_path}")
        print(df_indices.head())

    # 2. FX (EUR vs GBP)
    print("\n--- Building FX Pair (EUR, GBP) ---")
    df_eur = process_asset("EURUSD", "4h")
    df_gbp = process_asset("GBPUSD", "4h")

    if df_eur is not None and df_gbp is not None:
        print("Aligning FX...")
        df_fx = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_fx_4h.parquet")
        df_fx.write_parquet(out_path)
        print(f"Saved FX: {len(df_fx)} rows to {out_path}")
        print(df_fx.head())

    # 3. Dow (UDX) vs SPX (Value vs Growth)
    print("\n--- Building Dow Pair (UDX, SPX) ---")
    df_udx = process_asset("UDXUSD", "4h")
    # reuse df_spx from above if possible, but safely re-load/process if memory allows or if not persisted in scope perfectly
    # Actually df_spx is local to build_pairs, so it exists.

    if df_udx is not None and df_spx is not None:
        print("Aligning Dow/SPX...")
        df_dow = df_udx.join(df_spx, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_dow_spx_4h.parquet")
        df_dow.write_parquet(out_path)
        print(f"Saved Dow: {len(df_dow)} rows to {out_path}")

    # 4. DAX (GRX) vs FTSE (UKX) (Europe)
    print("\n--- Building Euro Pair (DAX, FTSE) ---")
    df_grx = process_asset("GRXEUR", "4h")
    df_ukx = process_asset("UKXGBP", "4h")

    if df_grx is not None and df_ukx is not None:
        print("Aligning DAX/FTSE...")
        df_euro = df_grx.join(df_ukx, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_dax_ftse_4h.parquet")
        df_euro.write_parquet(out_path)
        print(f"Saved Euro: {len(df_euro)} rows to {out_path}")

    # 5. AUD/NZD (Aussie Kiwi)
    print("\n--- Building AUD/NZD ---")
    df_aud = process_asset("AUDNZD", "4h")
    # Actually AUDNZD is a single asset? Yes, it's a cross pair tick stream.
    # PRO TIP: We can trade the CROSS itself using Mean Reversion on Price,
    # OR we can trade AUDUSD vs NZDUSD.
    # The user asked for "Pairs Approach" (Kalman).
    # Kalman works on X vs Y.
    # Let's try AUDUSD vs NZDUSD for the "Arb".
    # BUT, if we have the cross `AUDNZD`, we can just trade the cross directly?
    # No, Kalman is for constructing a synthetic stationary spread from two non-stationary assets.
    # Trading a Cross directly is just trading a Forex pair.
    # Let's see if we have AUDUSD and NZDUSD.
    # I saw AUDUSD in the list. I saw NZDUSD in the list.

    # Let's prioritize AUDUSD vs NZDUSD.
    df_audusd = process_asset("AUDUSD", "4h")
    df_nzdusd = process_asset("NZDUSD", "4h")

    if df_audusd is not None and df_nzdusd is not None:
        print("Aligning AUD/NZD (Synthetic)...")
        df_an = df_audusd.join(df_nzdusd, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_aud_nzd_4h.parquet")
        df_an.write_parquet(out_path)
        print(f"Saved AUD/NZD: {len(df_an)} rows to {out_path}")

    # 6. EUR/CHF (Synthetic or Cross?)
    # We have EURCHF tick data.
    # But let's stick to the "Kalman Pair" logic: EURUSD vs USDCHF(inverted)?
    # Or EURUSD vs ... ?
    # Actually, EURCHF is the pair.
    # If we want to use Kalman, we usually want two cointegrated assets.
    # E.g. EURUSD vs GBPUSD works.
    # EURUSD vs CHF? (USDCHF).
    # Note: EURCHF = EURUSD * USDCHF.
    # Let's try Kalman on EURUSD vs USDCHF (Inverse).
    # Or... EURUSD vs GBPUSD is verified.
    # Let's try AUDUSD vs USDCAD (Commodity Bloc).

    # User specifically asked about AUDNZD and EURCHF.
    # Let's check if we have USDCHF. Yes we do.
    # So we can do EURUSD vs USDCHF.
    df_usdchf = process_asset("USDCHF", "4h")
    # Note: Correlation is negative. EUR goes up, USDCHF goes down.
    # Kalman handles negative beta fine.

    if df_eur is not None and df_usdchf is not None:
         print("Aligning EUR/CHF (Synthetic)...")
         df_ec = df_eur.join(df_usdchf, on="timestamp", how="inner").sort("timestamp")
         out_path = os.path.join(OUTPUT_DIR, "pairs_eur_chf_4h.parquet")
         df_ec.write_parquet(out_path)
         print(f"Saved EUR/CHF: {len(df_ec)} rows to {out_path}")

    # 7. Oil (Brent BCO vs WTI)
    print("\n--- Building Oil Pair (Brent, WTI) ---")
    df_bco = process_asset("BCOUSD", "4h")
    df_wti = process_asset("WTIUSD", "4h")

    if df_bco is not None and df_wti is not None:
        print("Aligning Oil...")
        df_oil = df_bco.join(df_wti, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_oil_4h.parquet")
        df_oil.write_parquet(out_path)
        print(f"Saved Oil: {len(df_oil)} rows to {out_path}")

    # 8. Metals (Gold/Silver)
    print("\n--- Building Metals Pair (Gold, Silver) ---")
    df_xau = process_asset("XAUUSD", "4h")
    df_xag = process_asset("XAGUSD", "4h")

    if df_xau is not None and df_xag is not None:
        print("Aligning Metals...")
        df_metals = df_xau.join(df_xag, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_metals_4h.parquet")
        df_metals.write_parquet(out_path)
        print(f"Saved Metals: {len(df_metals)} rows to {out_path}")

    # 9. Yen (USDJPY vs EURJPY)
    print("\n--- Building Yen Pair (USDJPY, EURJPY) ---")
    df_usdjpy = process_asset("USDJPY", "4h")
    df_eurjpy = process_asset("EURJPY", "4h")

    if df_usdjpy is not None and df_eurjpy is not None:
        print("Aligning Yen...")
        df_yen = df_usdjpy.join(df_eurjpy, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_yen_4h.parquet")
        df_yen.write_parquet(out_path)
        print(f"Saved Yen: {len(df_yen)} rows to {out_path}")

    # 10. Oil/CAD (Brent vs USDCAD)
    print("\n--- Building Oil/CAD Pair (BCO, USDCAD) ---")
    df_bco = process_asset("BCOUSD", "4h")
    df_usdcad = process_asset("USDCAD", "4h")

    if df_bco is not None and df_usdcad is not None:
        print("Aligning Oil/CAD...")
        df_oilcad = df_bco.join(df_usdcad, on="timestamp", how="inner").sort("timestamp")
        out_path = os.path.join(OUTPUT_DIR, "pairs_oil_cad_4h.parquet")
        df_oilcad.write_parquet(out_path)
        print(f"Saved Oil/CAD: {len(df_oilcad)} rows to {out_path}")

if __name__ == "__main__":
    build_pairs()
