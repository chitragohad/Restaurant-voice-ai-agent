"""Google Calendar integration for tentative dining holds."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import pytz
from googleapiclient.discovery import build

from .google_auth import get_credentials
from .google_errors import format_google_api_error

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


class CalendarService:
    def __init__(self) -> None:
        self._calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        creds = get_credentials()
        self._service = build("calendar", "v3", credentials=creds) if creds else None
        self._mock = os.getenv("MOCK_GOOGLE_INTEGRATIONS", "false").lower() == "true"

    def create_tentative_hold(
        self,
        occasion: str,
        code: str,
        slot_datetime: datetime,
        duration_minutes: int = 90,
    ) -> dict:
        """Create a tentative calendar hold for the reservation."""
        title = f"Dining Hold — {occasion} — {code}"
        if slot_datetime.tzinfo is None:
            slot_datetime = IST.localize(slot_datetime)
        else:
            slot_datetime = slot_datetime.astimezone(IST)

        end = slot_datetime + timedelta(minutes=duration_minutes)

        if self._mock:
            mock_id = f"mock-event-{code}"
            logger.info("[MOCK] Calendar hold: %s at %s", title, slot_datetime)
            return {
                "success": True,
                "event_id": mock_id,
                "title": title,
                "start_ist": slot_datetime.strftime("%Y-%m-%d %H:%M IST"),
                "mock": True,
            }

        if self._service is None:
            msg = (
                "Google credentials missing. Run OAuth setup and ensure token.json exists."
            )
            logger.error("Calendar hold skipped: %s", msg)
            return {"success": False, "error": msg}

        event = {
            "summary": title,
            "description": (
                f"Tentative table hold for Shiv Sagar.\n"
                f"Reservation code: {code}\n"
                f"Occasion: {occasion}\n"
                f"Table held for 15 minutes from reservation time."
            ),
            "start": {
                "dateTime": slot_datetime.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "status": "tentative",
            "transparency": "opaque",
        }

        try:
            created = (
                self._service.events()
                .insert(calendarId=self._calendar_id, body=event)
                .execute()
            )
            return {
                "success": True,
                "event_id": created["id"],
                "title": title,
                "start_ist": slot_datetime.strftime("%Y-%m-%d %H:%M IST"),
            }
        except Exception as exc:
            logger.exception("Calendar create failed")
            return {"success": False, "error": format_google_api_error(exc)}

    def delete_hold(self, event_id: str) -> dict:
        if self._mock or self._service is None:
            logger.info("[MOCK] Deleted calendar event %s", event_id)
            return {"success": True, "mock": True}

        try:
            self._service.events().delete(
                calendarId=self._calendar_id, eventId=event_id
            ).execute()
            return {"success": True}
        except Exception as exc:
            logger.exception("Calendar delete failed")
            return {"success": False, "error": str(exc)}

    def update_hold(
        self,
        event_id: str,
        occasion: str,
        code: str,
        slot_datetime: datetime,
    ) -> dict:
        if self._mock or self._service is None:
            logger.info("[MOCK] Updated calendar event %s", event_id)
            return {"success": True, "mock": True}

        title = f"Dining Hold — {occasion} — {code}"
        end = slot_datetime + timedelta(minutes=90)
        body = {
            "summary": title,
            "start": {
                "dateTime": slot_datetime.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
        }
        try:
            self._service.events().patch(
                calendarId=self._calendar_id, eventId=event_id, body=body
            ).execute()
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": format_google_api_error(exc)}

    def check_connection(self) -> dict:
        if self._mock:
            return {"ok": True, "mock": True}
        if self._service is None:
            return {
                "ok": False,
                "error": "Google OAuth token missing. Complete OAuth setup (credentials.json + token.json).",
            }
        try:
            self._service.calendarList().list(maxResults=1).execute()
            return {"ok": True, "calendar_id": self._calendar_id}
        except Exception as exc:
            return {"ok": False, "error": format_google_api_error(exc)}
