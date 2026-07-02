"""Mock table inventory for Shiv Sagar restaurant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")

# Lunch 12:00–15:30, Dinner 18:30–22:30 (IST)
SLOT_TIMES = [
    time(12, 0),
    time(12, 30),
    time(13, 0),
    time(13, 30),
    time(14, 0),
    time(14, 30),
    time(15, 0),
    time(18, 30),
    time(19, 0),
    time(19, 30),
    time(20, 0),
    time(20, 30),
    time(21, 0),
    time(21, 30),
    time(22, 0),
]

# Occasion → how many tables we hold in mock inventory per slot
OCCASION_CAPACITY = {
    "standard_dining": 8,
    "large_group_6_plus": 3,
    "outdoor_patio": 4,
    "special_occasion": 2,
    "bar_lounge": 6,
}


class DiningOccasion(str, Enum):
    STANDARD_DINING = "standard_dining"
    LARGE_GROUP_6_PLUS = "large_group_6_plus"
    OUTDOOR_PATIO = "outdoor_patio"
    SPECIAL_OCCASION = "special_occasion"
    BAR_LOUNGE = "bar_lounge"

    @classmethod
    def from_label(cls, label: str) -> Optional["DiningOccasion"]:
        mapping = {
            "standard dining": cls.STANDARD_DINING,
            "standard": cls.STANDARD_DINING,
            "large group": cls.LARGE_GROUP_6_PLUS,
            "large group 6+": cls.LARGE_GROUP_6_PLUS,
            "6+": cls.LARGE_GROUP_6_PLUS,
            "outdoor": cls.OUTDOOR_PATIO,
            "patio": cls.OUTDOOR_PATIO,
            "outdoor/patio": cls.OUTDOOR_PATIO,
            "special occasion": cls.SPECIAL_OCCASION,
            "anniversary": cls.SPECIAL_OCCASION,
            "special occasion/anniversary": cls.SPECIAL_OCCASION,
            "bar": cls.BAR_LOUNGE,
            "lounge": cls.BAR_LOUNGE,
            "bar/lounge": cls.BAR_LOUNGE,
        }
        return mapping.get(label.strip().lower())

    @property
    def display_name(self) -> str:
        names = {
            DiningOccasion.STANDARD_DINING: "Standard Dining",
            DiningOccasion.LARGE_GROUP_6_PLUS: "Large Group (6+)",
            DiningOccasion.OUTDOOR_PATIO: "Outdoor/Patio",
            DiningOccasion.SPECIAL_OCCASION: "Special Occasion/Anniversary",
            DiningOccasion.BAR_LOUNGE: "Bar/Lounge",
        }
        return names[self]


@dataclass(frozen=True)
class TimeSlot:
    date: date
    slot_time: time
    occasion: DiningOccasion

    @property
    def datetime_ist(self) -> datetime:
        return IST.localize(datetime.combine(self.date, self.slot_time))

    def format_ist(self) -> str:
        dt = self.datetime_ist
        return dt.strftime("%A, %d %B %Y at %I:%M %p IST")


class SlotInventory:
    """Tracks booked slots against mock capacity."""

    def __init__(self) -> None:
        self._booked: dict[tuple[date, time, DiningOccasion], int] = {}

    def _capacity(self, occasion: DiningOccasion) -> int:
        return OCCASION_CAPACITY[occasion.value]

    def _booked_count(
        self, d: date, slot_time: time, occasion: DiningOccasion
    ) -> int:
        return self._booked.get((d, slot_time, occasion), 0)

    def is_available(self, slot: TimeSlot) -> bool:
        return (
            self._booked_count(slot.date, slot.slot_time, slot.occasion)
            < self._capacity(slot.occasion)
        )

    def book(self, slot: TimeSlot) -> bool:
        if not self.is_available(slot):
            return False
        key = (slot.date, slot.slot_time, slot.occasion)
        self._booked[key] = self._booked.get(key, 0) + 1
        return True

    def release(self, slot: TimeSlot) -> None:
        key = (slot.date, slot.slot_time, slot.occasion)
        if key not in self._booked:
            return
        self._booked[key] -= 1
        if self._booked[key] <= 0:
            del self._booked[key]

    def available_slots_for_day(
        self, d: date, occasion: DiningOccasion
    ) -> list[TimeSlot]:
        return [
            TimeSlot(d, t, occasion)
            for t in SLOT_TIMES
            if self.is_available(TimeSlot(d, t, occasion))
        ]

    def find_nearest_slots(
        self,
        preferred: datetime,
        occasion: DiningOccasion,
        count: int = 2,
        search_days: int = 7,
    ) -> list[TimeSlot]:
        """Return up to `count` available slots closest to preferred time."""
        preferred_ist = preferred
        if preferred_ist.tzinfo is None:
            preferred_ist = IST.localize(preferred_ist)
        else:
            preferred_ist = preferred_ist.astimezone(IST)

        candidates: list[tuple[float, TimeSlot]] = []
        base_date = preferred_ist.date()

        for day_offset in range(search_days):
            d = base_date + timedelta(days=day_offset)
            for slot in self.available_slots_for_day(d, occasion):
                delta = abs(
                    (slot.datetime_ist - preferred_ist).total_seconds()
                )
                candidates.append((delta, slot))

        candidates.sort(key=lambda x: x[0])
        return [slot for _, slot in candidates[:count]]

    def exact_slot(
        self, d: date, slot_time: time, occasion: DiningOccasion
    ) -> Optional[TimeSlot]:
        slot = TimeSlot(d, slot_time, occasion)
        return slot if self.is_available(slot) else None
