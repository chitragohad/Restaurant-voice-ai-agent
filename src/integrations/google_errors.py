"""Extract actionable messages from Google API errors."""

from __future__ import annotations


def format_google_api_error(exc: Exception) -> str:
    try:
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError):
            content = (
                exc.content.decode("utf-8", errors="replace")
                if exc.content
                else str(exc)
            )
            if "accessNotConfigured" in content or "has not been used" in content:
                if "calendar" in content.lower():
                    return (
                        "Google Calendar API is not enabled for your Cloud project. "
                        "Enable it at: "
                        "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com"
                    )
                if "sheets" in content.lower():
                    return (
                        "Google Sheets API is not enabled for your Cloud project. "
                        "Enable it at: "
                        "https://console.cloud.google.com/apis/library/sheets.googleapis.com"
                    )
            if "Unable to parse range" in content:
                return (
                    "Spreadsheet tab name not found. Set GOOGLE_SHEETS_SHEET_NAME "
                    "to an existing tab or let the app create one automatically."
                )
            return content[:500]
    except Exception:
        pass
    return str(exc)
