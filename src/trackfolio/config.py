"""Application configuration."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "trackfolio.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
BASE_CURRENCY = "EUR"
