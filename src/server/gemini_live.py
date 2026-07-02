"""Gemini Live API WebSocket bridge for browser voice sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import ssl
from typing import Any, Optional

import certifi
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from src.agent.gemini_tools import (
    execute_booking_tool_timed,
    get_function_declarations,
    tool_result_text,
)
from src.agent.prompts import SYSTEM_PROMPT
from src.server.latency_tracker import SessionLatencyTracker, get_latency_store

logger = logging.getLogger(__name__)

GEMINI_WS_BASE = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)
SETUP_TIMEOUT_SEC = float(os.getenv("GEMINI_SETUP_TIMEOUT_SEC", "45"))


def _sanitize_transcript(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<ctrl\d+>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[\u0000-\u001f\u007f-\u009f]", "", text)
    return " ".join(text.split())


def _is_mostly_english(text: str) -> bool:
    """True when transcript is primarily Latin letters (English UI)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    latin = sum(1 for c in letters if ord(c) < 128)
    return latin / len(letters) >= 0.85


def is_gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def _gemini_ws_url() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not configured. Copy .env.example to .env and add your key."
        )
    return f"{GEMINI_WS_BASE}?key={api_key}"


def build_setup_message() -> dict:
    model = os.getenv(
        "GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
    )
    if not model.startswith("models/"):
        model = f"models/{model}"

    voice = os.getenv("GEMINI_VOICE", "Aoede")

    return {
        "setup": {
            "model": model,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "languageCode": "en-US",
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice},
                    },
                },
            },
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "tools": [{"functionDeclarations": get_function_declarations()}],
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "disabled": False,
                    "startOfSpeechSensitivity": "START_SENSITIVITY_LOW",
                    "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                    "prefixPaddingMs": 20,
                    "silenceDurationMs": 300,
                },
                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
            },
        }
    }


def _extract_error(data: dict) -> Optional[str]:
    if "error" in data:
        err = data["error"]
        if isinstance(err, dict):
            return err.get("message") or str(err)
        return str(err)
    return None


async def _send_to_client(client_ws: WebSocket, payload: dict) -> None:
    await client_ws.send_json(payload)


async def _handle_tool_call(
    gemini_ws: websockets.WebSocketClientProtocol,
    tool_call: dict,
    tracker: SessionLatencyTracker,
) -> None:
    function_responses = []
    for fc in tool_call.get("functionCalls", []):
        name = fc.get("name", "")
        args = fc.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        result, breakdown = execute_booking_tool_timed(name, args)
        summary = tool_result_text(result)
        tracker.on_tool_call(
            name,
            args,
            breakdown.get("total_ms", 0.0),
            breakdown,
            summary,
        )
        function_responses.append(
            {
                "id": fc.get("id"),
                "name": name,
                "response": {"result": summary},
            }
        )

    await gemini_ws.send(
        json.dumps({"toolResponse": {"functionResponses": function_responses}})
    )


async def _process_gemini_message(
    data: dict,
    gemini_ws: websockets.WebSocketClientProtocol,
    client_ws: WebSocket,
    tracker: SessionLatencyTracker,
    setup_event: asyncio.Event,
    first_audio_seen: list[bool],
) -> None:
    err = _extract_error(data)
    if err:
        logger.error("Gemini error: %s", err)
        await _send_to_client(client_ws, {"type": "error", "message": err})
        raise RuntimeError(err)

    if "setupComplete" in data:
        setup_event.set()
        await _send_to_client(
            client_ws,
            {"type": "ready", "session_id": tracker.session_id},
        )
        logger.info("Sent ready to client for session %s", tracker.session_id)
        tracker.end_span(
            "setup",
            "gemini_setup",
            "gemini",
            input_text="setup message with SYSTEM_PROMPT + 4 tools + VAD",
            output_text="setupComplete",
        )
        tracker.mark(
            "session_ready",
            "server",
            output_text='{ "type": "ready", "session_id": "..." }',
        )
        return

    if data.get("toolCall"):
        await _handle_tool_call(gemini_ws, data["toolCall"], tracker)
        return

    server_content = data.get("serverContent") or {}

    if server_content.get("interrupted"):
        tracker.mark(
            "barge_in",
            "gemini",
            input_text="User speech detected during agent turn",
            output_text='{ "type": "interrupted" }',
        )
        await _send_to_client(client_ws, {"type": "interrupted"})
        return

    input_tx = server_content.get("inputTranscription")
    if input_tx and input_tx.get("text"):
        tx_text = _sanitize_transcript(input_tx["text"])
        if tx_text and _is_mostly_english(tx_text):
            tracker.on_user_transcript(tx_text, input_tx.get("finished", False))
            await _send_to_client(
                client_ws,
                {
                    "type": "transcript",
                    "role": "user",
                    "text": tx_text,
                    "finished": input_tx.get("finished", False),
                },
            )

    output_tx = server_content.get("outputTranscription")
    if output_tx and output_tx.get("text"):
        tx_text = _sanitize_transcript(output_tx["text"])
        if tx_text:
            tracker.on_agent_transcript(tx_text, output_tx.get("finished", False))
            await _send_to_client(
                client_ws,
                {
                    "type": "transcript",
                    "role": "agent",
                    "text": tx_text,
                    "finished": output_tx.get("finished", False),
                },
            )

    parts = (server_content.get("modelTurn") or {}).get("parts") or []
    for part in parts:
        inline = part.get("inlineData")
        if inline and inline.get("data"):
            if not first_audio_seen[0]:
                first_audio_seen[0] = True
                tracker.mark(
                    "first_agent_audio",
                    "gemini",
                    output_text="First agent audio chunk (greeting)",
                )
            tracker.on_first_agent_audio_after_wait()
            await _send_to_client(
                client_ws,
                {"type": "audio", "data": inline["data"]},
            )

    if server_content.get("turnComplete"):
        tracker.mark(
            "turn_complete",
            "gemini",
            output_text='{ "type": "turn_complete" }',
        )
        await _send_to_client(client_ws, {"type": "turn_complete"})


async def _process_client_message(
    message: dict,
    gemini_ws: websockets.WebSocketClientProtocol,
    tracker: SessionLatencyTracker,
    setup_event: asyncio.Event,
) -> None:
    msg_type = message.get("type")

    if msg_type == "latency_report":
        tracker.merge_client_report(message)
        return

    if not setup_event.is_set():
        return

    if msg_type == "audio" and message.get("data"):
        await gemini_ws.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "mediaChunks": [
                            {
                                "mimeType": "audio/pcm;rate=16000",
                                "data": message["data"],
                            }
                        ]
                    }
                }
            )
        )
    elif msg_type == "text" and message.get("text"):
        await gemini_ws.send(
            json.dumps(
                {
                    "clientContent": {
                        "turns": [
                            {
                                "role": "user",
                                "parts": [{"text": message["text"]}],
                            }
                        ],
                        "turnComplete": True,
                    }
                }
            )
        )


async def _run_voice_proxy(
    client_ws: WebSocket,
    gemini_ws: websockets.WebSocketClientProtocol,
    tracker: SessionLatencyTracker,
) -> None:
    """Phase 1: Gemini setup. Phase 2: bidirectional proxy."""
    setup_event = asyncio.Event()
    first_audio_seen = [False]

    tracker.start_span("setup")
    await gemini_ws.send(json.dumps(build_setup_message()))

    deadline = asyncio.get_event_loop().time() + SETUP_TIMEOUT_SEC
    while not setup_event.is_set():
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise RuntimeError(
                f"Gemini setup timed out after {SETUP_TIMEOUT_SEC:.0f}s."
            )
        raw = await asyncio.wait_for(gemini_ws.recv(), timeout=remaining)
        data = json.loads(raw)
        logger.info("Gemini setup response keys: %s", list(data.keys()))
        await _process_gemini_message(
            data,
            gemini_ws,
            client_ws,
            tracker,
            setup_event,
            first_audio_seen,
        )

    if not setup_event.is_set():
        raise RuntimeError("Gemini did not return setupComplete")

    # Brief nudge so the agent greets the caller when the session starts
    await gemini_ws.send(
        json.dumps(
            {
                "clientContent": {
                    "turns": [
                        {
                            "role": "user",
                            "parts": [{"text": "Hello."}],
                        }
                    ],
                    "turnComplete": True,
                }
            }
        )
    )

    while True:
        gemini_task = asyncio.create_task(gemini_ws.recv())
        client_task = asyncio.create_task(client_ws.receive_json())

        done, pending = await asyncio.wait(
            {gemini_task, client_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, WebSocketDisconnect):
                pass

        for task in done:
            if task is gemini_task:
                raw = task.result()
                data = json.loads(raw)
                await _process_gemini_message(
                    data,
                    gemini_ws,
                    client_ws,
                    tracker,
                    setup_event,
                    first_audio_seen,
                )
            else:
                try:
                    message = task.result()
                except WebSocketDisconnect:
                    return
                await _process_client_message(
                    message, gemini_ws, tracker, setup_event
                )


async def handle_voice_websocket(client_ws: WebSocket) -> None:
    await client_ws.accept()
    tracker = get_latency_store().create_tracker()
    tracker.mark(
        "ws_accept",
        "network",
        input_text="Browser WebSocket upgrade",
        output_text="Connection accepted",
    )

    if not is_gemini_configured():
        await _send_to_client(
            client_ws,
            {
                "type": "error",
                "message": (
                    "GEMINI_API_KEY is not configured. "
                    "Copy .env.example to .env, add your key, and restart the server."
                ),
            },
        )
        get_latency_store().finalize_tracker(tracker.session_id)
        await client_ws.close()
        return

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    gemini_ws: Optional[websockets.WebSocketClientProtocol] = None

    try:
        tracker.start_span("connect")
        gemini_ws = await websockets.connect(
            _gemini_ws_url(),
            ssl=ssl_context,
            max_size=10 * 1024 * 1024,
            open_timeout=15,
        )
        tracker.end_span(
            "connect",
            "gemini_wss_connect",
            "network",
            input_text="WSS generativelanguage.googleapis.com",
            output_text="TLS + WebSocket connected",
        )

        await _run_voice_proxy(client_ws, gemini_ws, tracker)

    except ValueError as exc:
        logger.warning("Voice session config error: %s", exc)
        await _send_to_client(client_ws, {"type": "error", "message": str(exc)})
    except (ConnectionClosed, WebSocketDisconnect) as exc:
        logger.info("Voice session disconnected: %s", exc)
    except Exception as exc:
        logger.exception("Voice session error")
        try:
            await _send_to_client(
                client_ws, {"type": "error", "message": f"Voice session error: {exc}"}
            )
        except Exception:
            pass
    finally:
        session = get_latency_store().finalize_tracker(tracker.session_id)
        if session:
            try:
                await _send_to_client(
                    client_ws,
                    {
                        "type": "session_summary",
                        "session_id": session["session_id"],
                        "total_ms": session["total_ms"],
                        "latency_url": f"/latency?session={session['session_id']}",
                    },
                )
            except Exception:
                pass
        if gemini_ws:
            await gemini_ws.close()
        try:
            await client_ws.close()
        except Exception:
            pass
