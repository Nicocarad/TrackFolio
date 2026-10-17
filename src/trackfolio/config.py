"""Application configuration."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "trackfolio.db"
DATABASE_URL = os.environ.get("TRACKFOLIO_DATABASE_URL", f"sqlite:///{DATABASE_PATH.as_posix()}")
