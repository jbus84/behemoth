#!/usr/bin/env python3
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.api.db import Base
from services.api.validation import compare_pipeline_to_db
from services.api.settings import settings

OUT = Path("data/analysis/db_reconcile_report.json")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    report = {}
    with Session() as session:
        for bar in ["m5", "m15"]:
            report[bar] = compare_pipeline_to_db(
                session,
                bar,
                match_ts=True,
                ts_tolerance_ns=0,
                match_pair=True,
            )
    OUT.write_text(json.dumps(report, indent=2))
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
