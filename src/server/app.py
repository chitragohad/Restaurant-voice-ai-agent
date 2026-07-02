"""FastAPI server: REST booking API + Gemini Live voice WebSocket + web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

IS_VERCEL = bool(os.getenv("VERCEL"))
if IS_VERCEL:
    os.environ.setdefault("RESERVATIONS_DATA_DIR", "/tmp/data")

from src.booking.reservations import get_reservation_service
from src.integrations.booking_actions import (
    cancel_calendar_hold,
    execute_booking_integrations,
    reschedule_integrations,
)

app = FastAPI(
    title="Shiv Sagar Voice Reservation Agent",
    description="Table booking voice agent with Google Calendar & Sheets integration",
    version="1.0.0",
)

STATIC_DIR = Path(__file__).parent / "static"
PUBLIC_DIR = ROOT / "public"

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AvailabilityRequest(BaseModel):
    occasion: str
    preferred_datetime: str


class BookRequest(BaseModel):
    occasion: str
    date: str
    time: str


class CancelRequest(BaseModel):
    code: str


class RescheduleRequest(BaseModel):
    code: str
    new_date: str
    new_time: str


def _page_dir() -> Path:
    return STATIC_DIR if STATIC_DIR.is_dir() else PUBLIC_DIR


@app.get("/")
async def index():
    return FileResponse(_page_dir() / "index.html")


@app.get("/architecture")
@app.get("/architecture.html")
async def architecture():
    return FileResponse(_page_dir() / "architecture.html")


@app.get("/latency")
@app.get("/latency.html")
async def latency():
    return FileResponse(_page_dir() / "latency.html")


@app.get("/api/latency/latest")
async def latency_latest():
    from src.server.latency_tracker import get_latency_store

    session = get_latency_store().latest()
    if not session:
        raise HTTPException(status_code=404, detail="No voice sessions recorded yet")
    return session


@app.get("/api/latency/sessions")
async def latency_sessions():
    from src.server.latency_tracker import get_latency_store

    return {"sessions": get_latency_store().list_sessions()}


@app.get("/api/latency/sessions/{session_id}")
async def latency_session(session_id: str):
    from src.server.latency_tracker import get_latency_store

    session = get_latency_store().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/integrations/status")
async def integrations_status():
    from src.integrations.calendar import CalendarService
    from src.integrations.sheets import SheetsService

    mock = os.getenv("MOCK_GOOGLE_INTEGRATIONS", "false").lower() == "true"
    calendar = CalendarService().check_connection()
    sheets = SheetsService().check_connection()
    return {
        "mock_mode": mock,
        "calendar": calendar,
        "sheets": sheets,
        "all_ok": (calendar.get("ok") and sheets.get("ok")) or mock,
    }


@app.get("/health")
async def health():
    from src.server.gemini_live import is_gemini_configured

    return {
        "status": "ok",
        "timezone": "Asia/Kolkata (IST)",
        "voice_configured": is_gemini_configured(),
    }


@app.get("/api/voice/status")
async def voice_status():
    from src.server.gemini_live import is_gemini_configured

    return {
        "configured": is_gemini_configured(),
        "model": os.getenv(
            "GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
        ),
    }


@app.get("/api/voice/test-gemini")
async def test_gemini_connection():
    """Diagnostic: verify Gemini Live WSS connect + setup."""
    import asyncio
    import json
    import ssl
    import time

    import certifi
    import websockets
    from src.server.gemini_live import (
        _gemini_ws_url,
        build_setup_message,
        is_gemini_configured,
    )

    if not is_gemini_configured():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not set")

    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        async with websockets.connect(
            _gemini_ws_url(), ssl=ctx, open_timeout=15
        ) as gemini_ws:
            connect_ms = round((time.perf_counter() - t0) * 1000, 1)
            await gemini_ws.send(json.dumps(build_setup_message()))
            raw = await asyncio.wait_for(gemini_ws.recv(), timeout=20)
            data = json.loads(raw)
            return {
                "ok": "setupComplete" in data,
                "connect_ms": connect_ms,
                "response_keys": list(data.keys()),
                "error": data.get("error"),
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "connect_ms": round((time.perf_counter() - t0) * 1000, 1)}


@app.post("/api/check-availability")
async def api_check_availability(req: AvailabilityRequest):
    return get_reservation_service().check_availability(
        req.occasion, req.preferred_datetime
    )


@app.post("/api/book")
async def api_book(req: BookRequest):
    result = get_reservation_service().book_new(req.occasion, req.date, req.time)
    if result.get("success"):
        result = execute_booking_integrations(result)
    return result


@app.post("/api/cancel")
async def api_cancel(req: CancelRequest):
    result = get_reservation_service().cancel_reservation(req.code)
    if result.get("success"):
        cancel_calendar_hold(req.code)
    return result


@app.post("/api/reschedule")
async def api_reschedule(req: RescheduleRequest):
    result = get_reservation_service().reschedule_reservation(
        req.code, req.new_date, req.new_time
    )
    if result.get("success"):
        reschedule_integrations(req.code, result)
    return result


@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """Gemini Live voice session — browser audio in/out with tool execution."""
    from src.server.gemini_live import handle_voice_websocket

    await handle_voice_websocket(websocket)


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)
    call_id: Optional[str] = None


@app.post("/api/realtime/execute-tool")
async def execute_realtime_tool(req: ToolCallRequest):
    """Execute a booking tool (REST fallback for integrations)."""
    from src.agent.gemini_tools import (
        execute_booking_tool,
        get_function_declarations,
        tool_result_text,
    )

    known = {d["name"] for d in get_function_declarations()}
    if req.name not in known:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {req.name}")

    result = execute_booking_tool(req.name, req.arguments)
    return {"result": tool_result_text(result)}
