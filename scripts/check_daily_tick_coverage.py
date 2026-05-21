#!/usr/bin/env python3
"""Check daily tick coverage inside parquet files, not just file existence."""

import argparse
from calendar import monthrange
from pathlib import Path

import pandas as pd


def check_symbol(symbol: str, tick_root: Path):
    symbol_dir = tick_root / symbol
    files = sorted(symbol_dir.glob(f"{symbol}_*_ticks.parquet"))
    issues = []

    for f in files:
        month_tag = f.stem.split('_')[1]
        year = int(month_tag[:4])
        month = int(month_tag[4:])
        expected_days = monthrange(year, month)[1]

        df = pd.read_parquet(f, columns=['timestamp'])
        df['date'] = pd.to_datetime(df['timestamp']).dt.date
        unique_days = df['date'].nunique()

        if unique_days < expected_days:
            missing_days = expected_days - unique_days
            issues.append({
                'file': f.name,
                'year': year,
                'month': month,
                'expected_days': expected_days,
                'actual_days': unique_days,
                'missing_days': missing_days,
                'min_date': df['date'].min(),
                'max_date': df['date'].max(),
                'total_ticks': len(df)
            })

    return issues

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='+', default=['EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDJPY', 'USDCHF'])
    parser.add_argument('--tick-root', default='/Users/danielfisher/Desktop/dukascopy_ticks')
    args = parser.parse_args()

    tick_root = Path(args.tick_root)
    all_issues = []

    for symbol in args.symbols:
        print(f"\n=== {symbol} ===")
        issues = check_symbol(symbol, tick_root)
        if issues:
            for issue in issues:
                print(f"  {issue['file']}: {issue['actual_days']}/{issue['expected_days']} days "
                      f"({issue['min_date']} to {issue['max_date']}) - "
                      f"{issue['missing_days']} days missing, {issue['total_ticks']} ticks")
                all_issues.append({**issue, 'symbol': symbol})
        else:
            print("  All months complete")

    if all_issues:
        print(f"\n\nTOTAL: {len(all_issues)} month-files with missing days across {len(args.symbols)} symbols")
    else:
        print("\n\nAll symbols have complete daily coverage!")

if __name__ == '__main__':
    main()
