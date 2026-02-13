
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.api.db import SessionLocal
from services.api.models import Position
from sqlalchemy import text

def reset_positions():
    db = SessionLocal()
    try:
        print("Resetting positions table...")
        # Use truncate for speed and ID reset
        db.execute(text("TRUNCATE TABLE positions RESTART IDENTITY CASCADE;"))
        db.commit()
        print("Positions table reset successfully.")
    except Exception as e:
        print(f"Error resetting DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_positions()
