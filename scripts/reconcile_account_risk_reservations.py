import sys
from pathlib import Path

# Add the repository root to sys.path to allow 'from scripts.X' package-style imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.reconcile_ftmo_reservations import *  # noqa: F401,F403
from scripts.reconcile_ftmo_reservations import main


if __name__ == "__main__":
    main()
