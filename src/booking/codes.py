"""Reservation code generation."""

from __future__ import annotations

import random
import string


def generate_reservation_code() -> str:
    """Generate a unique reservation code like TABLE-B99."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"TABLE-{suffix}"
