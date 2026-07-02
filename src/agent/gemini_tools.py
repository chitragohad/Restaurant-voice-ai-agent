"""Gemini Live API tool declarations and execution."""

from __future__ import annotations

import json
from typing import Any

from src.booking.reservations import get_reservation_service
from src.integrations.booking_actions import (
    cancel_calendar_hold,
    execute_booking_integrations,
    reschedule_integrations,
)


def get_function_declarations() -> list[dict]:
    return [
        {
            "name": "check_availability",
            "description": (
                "Check table availability for dining occasion and preferred datetime (IST). "
                "Returns exact slot or two nearest alternatives."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "occasion": {
                        "type": "string",
                        "description": "Standard Dining, Large Group 6+, Outdoor/Patio, etc.",
                    },
                    "preferred_datetime": {
                        "type": "string",
                        "description": "Preferred date/time in IST",
                    },
                },
                "required": ["occasion", "preferred_datetime"],
            },
        },
        {
            "name": "book_new",
            "description": (
                "Book a confirmed reservation. Creates calendar hold and sheet log. "
                "date: YYYY-MM-DD, time: HH:MM 24h IST."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "occasion": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                },
                "required": ["occasion", "date", "time"],
            },
        },
        {
            "name": "cancel_reservation",
            "description": "Cancel reservation by code (e.g. TABLE-B99).",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
        {
            "name": "reschedule_reservation",
            "description": "Reschedule reservation. new_date: YYYY-MM-DD, new_time: HH:MM IST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "new_date": {"type": "string"},
                    "new_time": {"type": "string"},
                },
                "required": ["code", "new_date", "new_time"],
            },
        },
    ]


def execute_booking_tool(name: str, args: dict) -> dict:
    result, _ = execute_booking_tool_timed(name, args)
    return result


def execute_booking_tool_timed(name: str, args: dict) -> tuple[dict, dict[str, float]]:
    import time

    svc = get_reservation_service()
    breakdown: dict[str, float] = {}

    if name == "check_availability":
        t0 = time.perf_counter()
        result = svc.check_availability(
            args.get("occasion", ""), args.get("preferred_datetime", "")
        )
        breakdown["inventory_lookup_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        breakdown["total_ms"] = breakdown["inventory_lookup_ms"]
        breakdown["success"] = bool(result.get("available") is not None or result.get("exact_match"))
        return result, breakdown

    if name == "book_new":
        t0 = time.perf_counter()
        result = svc.book_new(
            args.get("occasion", ""), args.get("date", ""), args.get("time", "")
        )
        breakdown["booking_logic_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if result.get("success"):
            t1 = time.perf_counter()
            result = execute_booking_integrations(result)
            breakdown["integrations_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        breakdown["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        breakdown["success"] = bool(result.get("success"))
        return result, breakdown

    if name == "cancel_reservation":
        t0 = time.perf_counter()
        result = svc.cancel_reservation(args.get("code", ""))
        breakdown["cancel_logic_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if result.get("success"):
            t1 = time.perf_counter()
            cancel_calendar_hold(args.get("code", ""))
            breakdown["calendar_delete_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        breakdown["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        breakdown["success"] = bool(result.get("success"))
        return result, breakdown

    if name == "reschedule_reservation":
        t0 = time.perf_counter()
        result = svc.reschedule_reservation(
            args.get("code", ""),
            args.get("new_date", ""),
            args.get("new_time", ""),
        )
        breakdown["reschedule_logic_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if result.get("success"):
            t1 = time.perf_counter()
            reschedule_integrations(args.get("code", ""), result)
            breakdown["integrations_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        breakdown["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        breakdown["success"] = bool(result.get("success"))
        return result, breakdown

    return {"success": False, "error": f"Unknown tool: {name}"}, {"total_ms": 0.0, "success": False}


def tool_result_text(result: dict) -> str:
    return json.dumps(result, indent=2)
