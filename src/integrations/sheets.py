"""Google Sheets integration for Daily Reservation Log."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import pytz
from googleapiclient.discovery import build

from .google_auth import get_credentials
from .google_errors import format_google_api_error

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")
HEADER_ROW = [
    "Logged At (IST)",
    "Action",
    "Date",
    "Occasion",
    "Slot (IST)",
    "Code",
]


class SheetsService:
    def __init__(self) -> None:
        self._spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        self._sheet_name = os.getenv(
            "GOOGLE_SHEETS_SHEET_NAME", "Daily Reservation Log"
        )
        self._resolved_sheet_name: Optional[str] = None
        creds = get_credentials()
        self._service = build("sheets", "v4", credentials=creds) if creds else None
        self._mock = os.getenv("MOCK_GOOGLE_INTEGRATIONS", "false").lower() == "true"

    def _sheet_range(self, cell_range: str) -> str:
        title = self._resolved_sheet_name or self._sheet_name
        escaped = title.replace("'", "''")
        return f"'{escaped}'!{cell_range}"

    def _resolve_sheet_tab(self) -> Optional[str]:
        if self._resolved_sheet_name:
            return self._resolved_sheet_name
        if not self._service or not self._spreadsheet_id:
            return None

        meta = (
            self._service.spreadsheets()
            .get(spreadsheetId=self._spreadsheet_id)
            .execute()
        )
        titles = [
            sheet["properties"]["title"] for sheet in meta.get("sheets", [])
        ]

        if self._sheet_name in titles:
            self._resolved_sheet_name = self._sheet_name
            return self._resolved_sheet_name

        if titles:
            fallback = titles[0]
            logger.warning(
                "Sheet tab '%s' not found; using '%s'. "
                "Update GOOGLE_SHEETS_SHEET_NAME or rename the tab.",
                self._sheet_name,
                fallback,
            )
            self._resolved_sheet_name = fallback
            return self._resolved_sheet_name

        try:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=self._spreadsheet_id,
                body={
                    "requests": [
                        {"addSheet": {"properties": {"title": self._sheet_name}}}
                    ]
                },
            ).execute()
            self._resolved_sheet_name = self._sheet_name
            return self._resolved_sheet_name
        except Exception as exc:
            logger.exception("Could not create sheet tab '%s'", self._sheet_name)
            self._last_error = format_google_api_error(exc)
            return None

    def append_reservation_log(
        self,
        date_str: str,
        occasion: str,
        slot_display: str,
        code: str,
        action: str = "BOOKED",
    ) -> dict:
        """Append a row to the Daily Reservation Log."""
        row = [
            datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
            action,
            date_str,
            occasion,
            slot_display,
            code,
        ]

        if self._mock:
            logger.info("[MOCK] Sheets append: %s", row)
            return {"success": True, "row": row, "mock": True}

        if self._service is None:
            msg = (
                "Google credentials missing. Run OAuth setup and ensure token.json exists."
            )
            logger.error("Sheets append skipped: %s", msg)
            return {"success": False, "error": msg}

        if not self._spreadsheet_id:
            msg = "GOOGLE_SHEETS_SPREADSHEET_ID is not set in .env"
            logger.error("Sheets append skipped: %s", msg)
            return {"success": False, "error": msg}

        if not self._resolve_sheet_tab():
            return {
                "success": False,
                "error": getattr(self, "_last_error", "Could not resolve sheet tab"),
            }

        self.ensure_header_row()

        body = {"values": [row]}

        try:
            self._service.spreadsheets().values().append(
                spreadsheetId=self._spreadsheet_id,
                range=self._sheet_range("A:F"),
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            return {
                "success": True,
                "row": row,
                "sheet": self._resolved_sheet_name,
            }
        except Exception as exc:
            logger.exception("Sheets append failed")
            return {"success": False, "error": format_google_api_error(exc)}

    def log_cancellation(self, reservation: dict) -> dict:
        return self.append_reservation_log(
            date_str=reservation.get("date", ""),
            occasion=reservation.get("occasion", ""),
            slot_display=reservation.get("slot_ist", ""),
            code=reservation.get("code", ""),
            action="CANCELLED",
        )

    def ensure_header_row(self) -> None:
        """Create header row if the target sheet tab is empty."""
        if self._mock or self._service is None or not self._spreadsheet_id:
            return
        if not self._resolve_sheet_tab():
            return

        try:
            existing = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    range=self._sheet_range("A1:F1"),
                )
                .execute()
            )
            if existing.get("values"):
                return
        except Exception:
            pass

        try:
            self._service.spreadsheets().values().update(
                spreadsheetId=self._spreadsheet_id,
                range=self._sheet_range("A1:F1"),
                valueInputOption="USER_ENTERED",
                body={"values": [HEADER_ROW]},
            ).execute()
        except Exception:
            logger.warning("Could not write sheet header — sheet may need manual setup")

    def check_connection(self) -> dict:
        if self._mock:
            return {"ok": True, "mock": True}
        if self._service is None:
            return {
                "ok": False,
                "error": "Google OAuth token missing. Complete OAuth setup (credentials.json + token.json).",
            }
        if not self._spreadsheet_id:
            return {"ok": False, "error": "GOOGLE_SHEETS_SPREADSHEET_ID is not set."}
        try:
            tab = self._resolve_sheet_tab()
            if not tab:
                return {"ok": False, "error": getattr(self, "_last_error", "No sheet tab")}
            meta = (
                self._service.spreadsheets()
                .get(spreadsheetId=self._spreadsheet_id, fields="properties.title")
                .execute()
            )
            return {
                "ok": True,
                "spreadsheet_title": meta.get("properties", {}).get("title"),
                "sheet_tab": tab,
            }
        except Exception as exc:
            return {"ok": False, "error": format_google_api_error(exc)}
