"""Shared setup: make the repo root importable (so `backend` and `api` import as in the app)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
