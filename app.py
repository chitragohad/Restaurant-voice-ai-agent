"""Vercel entrypoint — re-exports the FastAPI application."""

from src.server.app import app  # noqa: F401
