"""Shared Google OAuth helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_path(env_key: str, default: str) -> Path:
    raw = os.getenv(env_key, default)
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _credentials_from_service_account_file() -> Optional[Credentials]:
    """Load service account from GOOGLE_SERVICE_ACCOUNT_PATH."""
    from google.oauth2 import service_account

    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "").strip()
    if not raw:
        raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not raw:
        return None

    sa_path = Path(raw)
    if not sa_path.is_absolute():
        sa_path = PROJECT_ROOT / sa_path
    if not sa_path.exists():
        return None

    return service_account.Credentials.from_service_account_file(
        str(sa_path),
        scopes=SCOPES,
    )


def _credentials_from_env() -> Optional[Credentials]:
    """Production credentials from Vercel environment variables."""
    sa_file = _credentials_from_service_account_file()
    if sa_file:
        return sa_file

    refresh = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if refresh and client_id and client_secret:
        creds = Credentials(
            token=None,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds

    sa_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if sa_json:
        from google.oauth2 import service_account

        info = json.loads(sa_json)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    return None


def get_credentials() -> Optional[Credentials]:
    if os.getenv("MOCK_GOOGLE_INTEGRATIONS", "false").lower() == "true":
        return None

    env_creds = _credentials_from_env()
    if env_creds:
        return env_creds

    creds_path = _resolve_path("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    token_path = _resolve_path("GOOGLE_TOKEN_PATH", "token.json")

    if not creds_path.exists():
        return None

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.getenv("VERCEL"):
            return None
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        if creds and not os.getenv("VERCEL"):
            token_path.write_text(creds.to_json())

    return creds
