"""Unit tests for booking service."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["MOCK_GOOGLE_INTEGRATIONS"] = "true"

from src.booking.inventory import SlotInventory, DiningOccasion, TimeSlot
from src.booking.reservations import ReservationService
from src.booking.codes import generate_reservation_code
from datetime import date, time, datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")


def test_generate_code_format():
    code = generate_reservation_code()
    assert code.startswith("TABLE-")
    assert len(code) == 9


def test_exact_slot_available():
    inv = SlotInventory()
    d = date(2026, 7, 4)
    slot = TimeSlot(d, time(19, 0), DiningOccasion.SPECIAL_OCCASION)
    assert inv.is_available(slot)
    assert inv.book(slot)
    assert inv.is_available(slot)  # capacity 2 for special occasion
    assert inv.book(slot)
    assert not inv.is_available(slot)


def test_find_nearest_slots():
    inv = SlotInventory()
    preferred = IST.localize(datetime(2026, 7, 4, 19, 0))
    slots = inv.find_nearest_slots(preferred, DiningOccasion.STANDARD_DINING, count=2)
    assert len(slots) == 2


def test_book_new_flow():
    svc = ReservationService(SlotInventory())
    avail = svc.check_availability("Standard Dining", "2026-07-04 19:00")
    assert avail["success"]
    result = svc.book_new("Standard Dining", "2026-07-04", "19:00")
    assert result["success"]
    assert result["code"].startswith("TABLE-")
    cancel = svc.cancel_reservation(result["code"])
    assert cancel["success"]


if __name__ == "__main__":
    test_generate_code_format()
    test_exact_slot_available()
    test_find_nearest_slots()
    test_book_new_flow()
    print("All tests passed.")
