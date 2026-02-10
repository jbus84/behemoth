#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.getcwd())

from services.api.db import Base
from services.api.models import Position, PositionStatus, Side, ActiveLeg
from services.api import validation

OUT = Path("data/analysis/db_prediction_alignment.json")
DB_PATH = Path("data/analysis/api_validation.sqlite")


def _compute_exit_ts(df: pd.DataFrame, bar_minutes: int) -> pd.Series:
    bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
    durations = df["duration_bars"].astype(int)
    timeout_adjust = (durations >= 500).astype(int)
    return df["timestamp"].astype("int64") + ((durations - timeout_adjust) * bar_ns)


def _insert_positions(session, df: pd.DataFrame, bar: str):
    rows = []
    for row in df.itertuples(index=False):
        rows.append(
            Position(
                strategy_id=f"pipeline_{bar}",
                pair=row.pair,
                side=Side(row.side),
                active_leg=ActiveLeg(row.active_leg),
                status=PositionStatus.CLOSED,
                size=1.0,
                pnl_bps=float(row.pnl_bps),
                exit_ts=pd.to_datetime(int(row.exit_ts), unit="ns", utc=True),
            )
        )
    session.bulk_save_objects(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--guardrail", action="store_true", help="apply loss-streak guardrail before comparing")
    parser.add_argument("--database-url", default=None, help="override database URL (defaults to sqlite file)")
    args = parser.parse_args()

    out_path = OUT
    if args.guardrail:
        out_path = Path("data/analysis/db_prediction_alignment_guardrail.json")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    db_url = args.database_url or os.getenv("DATABASE_URL")
    if db_url:
        engine = create_engine(db_url)
    else:
        engine = create_engine(f"sqlite+pysqlite:///{DB_PATH}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    report = {}
    for bar in ["m5", "m15"]:
        bar_minutes = 5 if bar == "m5" else 15
        path = validation.PIPELINE_PATHS[bar]
        report[bar] = {}
        with Session() as session:
            session.query(Position).delete()
            session.commit()
            for chunk in pd.read_csv(
                path,
                usecols=["pair", "timestamp", "duration_bars", "pnl_bps", "side", "active_leg"],
                chunksize=50000,
            ):
                chunk = chunk.copy()
                chunk["exit_ts"] = _compute_exit_ts(chunk, bar_minutes)
                _insert_positions(session, chunk, bar)
                session.commit()

            report[bar] = validation.compare_pipeline_to_db(
                session,
                bar,
                match_ts=True,
                ts_tolerance_ns=0,
                match_pair=True,
                guardrail=args.guardrail,
            )

    out_path.write_text(json.dumps(report, indent=2))
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
