"""config.py - loads settings from the project-root .env file."""
import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name, default):
    val = os.getenv(name)
    return default if val is None else val.strip().lower() in ("1", "true", "yes", "on")


PORT = _int("NEUROSIGN_PORT", 5057)
DB_PATH = BACKEND_DIR / os.getenv("NEUROSIGN_DB_PATH", "neurosign.db")  # absolute paths also work
DEBUG = _bool("NEUROSIGN_DEBUG", False)
MODELS_DIR = BACKEND_DIR / "ml" / "models"
VOICE_MODEL_PATH = MODELS_DIR / "voice_rf.joblib"