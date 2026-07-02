"""
MCP server exposing restaurant booking integrations for Google Calendar and Sheets.

Requires Python 3.10+ and: pip install mcp>=1.0.0

Run: python -m mcp.restaurant_mcp_server
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.integrations.calendar import CalendarService
from src.integrations.sheets import SheetsService
from src.booking.reservations import get_reservation_service

server = Server("shiv-sagar-restaurant")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="calendar_create_hold",
            description="Create a tentative Google Calendar hold for a dining reservation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "occasion": {"type": "string"},
                    "code": {"type": "string"},
                    "slot_datetime_iso": {
                        "type": "string",
                        "description": "ISO datetime in IST",
                    },
                },
                "required": ["occasion", "code", "slot_datetime_iso"],
            },
        ),
        Tool(
            name="calendar_delete_hold",
            description="Delete a calendar hold by event ID.",
            inputSchema={
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        ),
        Tool(
            name="sheets_append_reservation",
            description="Append a row to the Daily Reservation Log spreadsheet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "occasion": {"type": "string"},
                    "slot": {"type": "string"},
                    "code": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["BOOKED", "CANCELLED", "RESCHEDULED"],
                    },
                },
                "required": ["date", "occasion", "slot", "code"],
            },
        ),
        Tool(
            name="check_availability",
            description="Check table availability for a dining occasion and preferred time (IST).",
            inputSchema={
                "type": "object",
                "properties": {
                    "occasion": {"type": "string"},
                    "preferred_datetime": {"type": "string"},
                },
                "required": ["occasion", "preferred_datetime"],
            },
        ),
        Tool(
            name="book_new",
            description="Book a new table reservation and return a reservation code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "occasion": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                },
                "required": ["occasion", "date", "time"],
            },
        ),
        Tool(
            name="cancel_reservation",
            description="Cancel a reservation by its code (e.g. TABLE-B99).",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        ),
        Tool(
            name="reschedule_reservation",
            description="Reschedule an existing reservation to a new date and time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "new_date": {"type": "string"},
                    "new_time": {"type": "string"},
                },
                "required": ["code", "new_date", "new_time"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    svc = get_reservation_service()
    calendar = CalendarService()
    sheets = SheetsService()

    if name == "check_availability":
        result = svc.check_availability(
            arguments["occasion"], arguments["preferred_datetime"]
        )
    elif name == "book_new":
        result = svc.book_new(
            arguments["occasion"], arguments["date"], arguments["time"]
        )
        if result.get("success"):
            from src.integrations.booking_actions import execute_booking_integrations

            result = execute_booking_integrations(result)
    elif name == "cancel_reservation":
        result = svc.cancel_reservation(arguments["code"])
        if result.get("success"):
            from src.integrations.booking_actions import cancel_calendar_hold

            cancel_calendar_hold(arguments["code"])
    elif name == "reschedule_reservation":
        result = svc.reschedule_reservation(
            arguments["code"], arguments["new_date"], arguments["new_time"]
        )
        if result.get("success"):
            from src.integrations.booking_actions import reschedule_integrations

            reschedule_integrations(arguments["code"], result)
    elif name == "calendar_create_hold":
        from dateutil import parser as date_parser

        dt = date_parser.parse(arguments["slot_datetime_iso"])
        result = calendar.create_tentative_hold(
            arguments["occasion"], arguments["code"], dt
        )
    elif name == "calendar_delete_hold":
        result = calendar.delete_hold(arguments["event_id"])
    elif name == "sheets_append_reservation":
        result = sheets.append_reservation_log(
            arguments["date"],
            arguments["occasion"],
            arguments["slot"],
            arguments["code"],
            arguments.get("action", "BOOKED"),
        )
    else:
        result = {"success": False, "error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main() -> None:
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError:
        print(
            "Error: MCP requires Python 3.10+ and `pip install mcp>=1.0.0`",
            file=sys.stderr,
        )
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
