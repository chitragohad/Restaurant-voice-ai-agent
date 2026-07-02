"""Reservation CRUD and booking orchestration."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import pytz
from dateutil import parser as date_parser

from .codes import generate_reservation_code
from .inventory import DiningOccasion, IST, SlotInventory, TimeSlot

DATA_DIR = Path(
    os.getenv(
        "RESERVATIONS_DATA_DIR",
        str(Path(__file__).resolve().parents[2] / "data"),
    )
)
RESERVATIONS_FILE = DATA_DIR / "reservations.json"


@dataclass
class Reservation:
    code: str
    occasion: str
    date: str  # ISO date YYYY-MM-DD
    slot_time: str  # HH:MM
    status: str  # active | cancelled
    created_at: str
    calendar_event_id: Optional[str] = None

    def to_slot(self) -> TimeSlot:
        occasion = DiningOccasion(self.occasion)
        d = date.fromisoformat(self.date)
        parts = self.slot_time.split(":")
        slot_time = time(int(parts[0]), int(parts[1]))
        return TimeSlot(d, slot_time, occasion)

    def format_slot_ist(self) -> str:
        return self.to_slot().format_ist()


class ReservationService:
    def __init__(self, inventory: Optional[SlotInventory] = None) -> None:
        self.inventory = inventory or SlotInventory()
        self._reservations: dict[str, Reservation] = {}
        self._load()

    def _load(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if RESERVATIONS_FILE.exists():
            raw = json.loads(RESERVATIONS_FILE.read_text())
            items = raw if isinstance(raw, list) else raw.get("reservations", [])
            for item in items:
                r = Reservation(**item)
                self._reservations[r.code] = r
                if r.status == "active":
                    self.inventory.book(r.to_slot())

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._reservations.values()]
        RESERVATIONS_FILE.write_text(json.dumps(data, indent=2))

    def get(self, code: str) -> Optional[Reservation]:
        return self._reservations.get(code.upper())

    def check_availability(
        self,
        occasion_label: str,
        preferred_datetime: str,
    ) -> dict:
        occasion = DiningOccasion.from_label(occasion_label)
        if not occasion:
            return {
                "success": False,
                "message": "Please choose a dining occasion: Standard Dining, Large Group 6+, Outdoor/Patio, Special Occasion/Anniversary, or Bar/Lounge.",
            }

        try:
            preferred = date_parser.parse(preferred_datetime)
            if preferred.tzinfo is None:
                preferred = IST.localize(preferred)
            else:
                preferred = preferred.astimezone(IST)
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": "I could not understand that date and time. Please say something like 'Friday at 7 PM IST'.",
            }

        d = preferred.date()
        slot_time = time(preferred.hour, preferred.minute)
        exact = self.inventory.exact_slot(d, slot_time, occasion)

        if exact:
            return {
                "success": True,
                "exact_match": True,
                "slots": [self._slot_dict(exact)],
                "message": f"Your preferred slot is available: {exact.format_ist()}.",
            }

        alternatives = self.inventory.find_nearest_slots(preferred, occasion, count=2)
        if not alternatives:
            return {
                "success": True,
                "exact_match": False,
                "slots": [],
                "message": (
                    f"No tables are available near {preferred.strftime('%A, %d %B at %I:%M %p IST')} "
                    f"for {occasion.display_name}. Would you like to try another day?"
                ),
            }

        return {
            "success": True,
            "exact_match": False,
            "slots": [self._slot_dict(s) for s in alternatives],
            "message": (
                f"Your preferred time is not available. Here are two nearby options in IST: "
                + "; ".join(s.format_ist() for s in alternatives)
            ),
        }

    def book_new(
        self,
        occasion_label: str,
        date_str: str,
        time_str: str,
    ) -> dict:
        occasion = DiningOccasion.from_label(occasion_label)
        if not occasion:
            return {"success": False, "message": "Invalid dining occasion."}

        try:
            d = date.fromisoformat(date_str) if "-" in date_str else date_parser.parse(date_str).date()
            if ":" in time_str:
                parts = time_str.split(":")
                slot_time = time(int(parts[0]), int(parts[1]))
            else:
                parsed = date_parser.parse(time_str)
                slot_time = time(parsed.hour, parsed.minute)
        except (ValueError, TypeError):
            return {"success": False, "message": "Could not parse date or time."}

        slot = TimeSlot(d, slot_time, occasion)
        if not self.inventory.is_available(slot):
            alts = self.inventory.find_nearest_slots(
                slot.datetime_ist, occasion, count=2
            )
            return {
                "success": False,
                "message": "That slot is no longer available.",
                "alternatives": [self._slot_dict(s) for s in alts],
            }

        code = self._unique_code()
        self.inventory.book(slot)
        reservation = Reservation(
            code=code,
            occasion=occasion.value,
            date=d.isoformat(),
            slot_time=f"{slot_time.hour:02d}:{slot_time.minute:02d}",
            status="active",
            created_at=datetime.now(IST).isoformat(),
        )
        self._reservations[code] = reservation
        self._save()

        return {
            "success": True,
            "code": code,
            "occasion": occasion.display_name,
            "slot_ist": slot.format_ist(),
            "date": d.isoformat(),
            "time": f"{slot_time.hour:02d}:{slot_time.minute:02d}",
            "message": (
                f"Your reservation is confirmed! Code: {code}. "
                f"{occasion.display_name} on {slot.format_ist()}. "
                f"We will hold your table for 15 minutes. Have a great day!"
            ),
        }

    def cancel_reservation(self, code: str) -> dict:
        reservation = self.get(code)
        if not reservation:
            return {
                "success": False,
                "message": f"I could not find reservation {code.upper()}. Please check the code and try again.",
            }
        if reservation.status == "cancelled":
            return {
                "success": False,
                "message": f"Reservation {code.upper()} is already cancelled.",
            }

        self.inventory.release(reservation.to_slot())
        reservation.status = "cancelled"
        self._save()

        return {
            "success": True,
            "code": reservation.code,
            "message": (
                f"Reservation {reservation.code} for {reservation.format_slot_ist()} "
                f"has been cancelled. We hope to see you another time!"
            ),
        }

    def reschedule_reservation(
        self,
        code: str,
        new_date_str: str,
        new_time_str: str,
    ) -> dict:
        reservation = self.get(code)
        if not reservation:
            return {
                "success": False,
                "message": f"I could not find reservation {code.upper()}.",
            }
        if reservation.status == "cancelled":
            return {
                "success": False,
                "message": f"Reservation {code.upper()} is cancelled and cannot be rescheduled.",
            }

        occasion = DiningOccasion(reservation.occasion)
        try:
            d = date.fromisoformat(new_date_str) if "-" in new_date_str else date_parser.parse(new_date_str).date()
            parts = new_time_str.split(":")
            slot_time = time(int(parts[0]), int(parts[1]))
        except (ValueError, TypeError):
            return {"success": False, "message": "Could not parse the new date or time."}

        new_slot = TimeSlot(d, slot_time, occasion)
        if not self.inventory.is_available(new_slot):
            alts = self.inventory.find_nearest_slots(
                new_slot.datetime_ist, occasion, count=2
            )
            return {
                "success": False,
                "message": "That new slot is not available.",
                "alternatives": [self._slot_dict(s) for s in alts],
            }

        old_slot = reservation.to_slot()
        self.inventory.release(old_slot)
        self.inventory.book(new_slot)

        reservation.date = d.isoformat()
        reservation.slot_time = f"{slot_time.hour:02d}:{slot_time.minute:02d}"
        self._save()

        return {
            "success": True,
            "code": reservation.code,
            "slot_ist": new_slot.format_ist(),
            "message": (
                f"Reservation {reservation.code} has been moved to {new_slot.format_ist()}. "
                f"We will hold your table for 15 minutes. Have a great day!"
            ),
        }

    def set_calendar_event_id(self, code: str, event_id: str) -> None:
        r = self.get(code)
        if r:
            r.calendar_event_id = event_id
            self._save()

    def _unique_code(self) -> str:
        for _ in range(100):
            code = generate_reservation_code()
            if code not in self._reservations:
                return code
        raise RuntimeError("Could not generate unique reservation code")

    @staticmethod
    def _slot_dict(slot: TimeSlot) -> dict:
        return {
            "date": slot.date.isoformat(),
            "time": f"{slot.slot_time.hour:02d}:{slot.slot_time.minute:02d}",
            "display_ist": slot.format_ist(),
            "occasion": slot.occasion.display_name,
        }


# Singleton for agent tools
_service: Optional[ReservationService] = None


def get_reservation_service() -> ReservationService:
    global _service
    if _service is None:
        _service = ReservationService()
    return _service
