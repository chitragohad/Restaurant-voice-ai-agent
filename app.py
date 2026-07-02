"""Vercel entrypoint — re-exports the FastAPI application."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.server.app import app  # noqa: F401
