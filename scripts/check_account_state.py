
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.api.db import SessionLocal
from services.api.risk import get_or_create_account_state

def check_account():
    db = SessionLocal()
    try:
        # Check for both M5 and M15 strategies
        for bar in ["m5", "m15"]:
            state = get_or_create_account_state(db, f"mom_{bar}")
            print(f"Strategy: mom_{bar} | Equity: {state.equity} | Peak: {state.peak_equity}")
    finally:
        db.close()

if __name__ == "__main__":
    check_account()
