"""Orchestrate calendar + sheets on booking lifecycle events."""

from __future__ import annotations

import logging
from datetime import date, time

from src.booking.reservations import get_reservation_service
from .calendar import CalendarService
from .sheets import SheetsService

logger = logging.getLogger(__name__)


def execute_booking_integrations(booking_result: dict) -> dict:
    """After a successful book_new, create calendar hold and log to sheets."""
    if not booking_result.get("success"):
        return booking_result

    code = booking_result["code"]
    occasion = booking_result["occasion"]
    d = date.fromisoformat(booking_result["date"])
    parts = booking_result["time"].split(":")
    slot_time = time(int(parts[0]), int(parts[1]))

    from src.booking.inventory import DiningOccasion, TimeSlot

    occasion_enum = next(
        o for o in DiningOccasion if o.display_name == occasion
    )
    slot = TimeSlot(d, slot_time, occasion_enum)

    calendar = CalendarService()
    cal_result = calendar.create_tentative_hold(
        occasion=occasion,
        code=code,
        slot_datetime=slot.datetime_ist,
    )

    sheets = SheetsService()
    sheets_result = sheets.append_reservation_log(
        date_str=booking_result["date"],
        occasion=occasion,
        slot_display=booking_result["slot_ist"],
        code=code,
        action="BOOKED",
    )

    if cal_result.get("event_id"):
        get_reservation_service().set_calendar_event_id(
            code, cal_result["event_id"]
        )

    booking_result["integrations"] = {
        "calendar": cal_result,
        "sheets": sheets_result,
    }
    integration_errors = []
    if not cal_result.get("success"):
        integration_errors.append(
            f"Calendar: {cal_result.get('error', 'unknown error')}"
        )
    if not sheets_result.get("success"):
        integration_errors.append(
            f"Sheets: {sheets_result.get('error', 'unknown error')}"
        )
    if integration_errors:
        booking_result["integrations_ok"] = False
        booking_result["integration_errors"] = integration_errors
        logger.error(
            "Booking %s saved locally but Google integrations failed: %s",
            code,
            "; ".join(integration_errors),
        )
    else:
        booking_result["integrations_ok"] = True
    return booking_result


def cancel_calendar_hold(code: str) -> dict:
    service = get_reservation_service()
    reservation = service.get(code)
    if not reservation or not reservation.calendar_event_id:
        return {"success": True, "skipped": True}

    calendar = CalendarService()
    result = calendar.delete_hold(reservation.calendar_event_id)

    sheets = SheetsService()
    sheets.log_cancellation(
        {
            "date": reservation.date,
            "occasion": DiningOccasion_display(reservation.occasion),
            "slot_ist": reservation.format_slot_ist(),
            "code": reservation.code,
        }
    )
    return result


def DiningOccasion_display(value: str) -> str:
    from src.booking.inventory import DiningOccasion

    try:
        return DiningOccasion(value).display_name
    except ValueError:
        return value


def reschedule_integrations(code: str, booking_result: dict) -> dict:
    service = get_reservation_service()
    reservation = service.get(code)
    if not reservation:
        return booking_result

    if reservation.calendar_event_id:
        slot = reservation.to_slot()
        calendar = CalendarService()
        calendar.update_hold(
            reservation.calendar_event_id,
            DiningOccasion_display(reservation.occasion),
            code,
            slot.datetime_ist,
        )

    sheets = SheetsService()
    sheets.append_reservation_log(
        date_str=reservation.date,
        occasion=DiningOccasion_display(reservation.occasion),
        slot_display=booking_result.get("slot_ist", reservation.format_slot_ist()),
        code=code,
        action="RESCHEDULED",
    )
    return booking_result
