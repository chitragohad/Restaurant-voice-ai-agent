"""Capture and store real voice-session latency breakdowns."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

NODE_MAP = {
    "client": ["user", "voicejs"],
    "network": ["voicejs", "ws"],
    "server": ["ws", "geminiLive"],
    "gemini": ["geminiLive", "gemini"],
    "tool": ["gemini", "tools", "booking"],
    "integration": ["booking", "calendar", "sheets"],
    "storage": ["booking", "json"],
}


@dataclass
class LatencyEvent:
    name: str
    category: str
    at_ms: float
    duration_ms: Optional[float] = None
    input: str = ""
    output: str = ""
    nodes: list[str] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    user_says: Optional[str] = None
    agent_says: Optional[str] = None
    breakdown: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


class SessionLatencyTracker:
    """Per voice WebSocket session timing collector."""

    def __init__(self) -> None:
        self.session_id = uuid4().hex[:10]
        self.t0 = time.perf_counter()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.events: list[LatencyEvent] = []
        self.client_events: list[dict] = []
        self._spans: dict[str, float] = {}
        self._turn = 0
        self._awaiting_agent_audio = False
        self._user_turn_end_ms: Optional[float] = None
        self._tool_turn_end_ms: Optional[float] = None
        self.outcome: Optional[str] = None
        self.reservation_code: Optional[str] = None

    def _elapsed_ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000

    def start_span(self, key: str) -> None:
        self._spans[key] = time.perf_counter()

    def end_span(
        self,
        key: str,
        name: str,
        category: str,
        input_text: str = "",
        output_text: str = "",
        **kwargs: Any,
    ) -> float:
        start = self._spans.pop(key, None)
        duration_ms = (time.perf_counter() - start) * 1000 if start else 0.0
        nodes, flows = _category_topology(category, kwargs.get("extra_nodes"))
        self.events.append(
            LatencyEvent(
                name=name,
                category=category,
                at_ms=self._elapsed_ms(),
                duration_ms=round(duration_ms, 1),
                input=input_text,
                output=output_text,
                nodes=nodes,
                flows=flows,
                breakdown=kwargs.get("breakdown", {}),
                user_says=kwargs.get("user_says"),
                agent_says=kwargs.get("agent_says"),
                meta=kwargs.get("meta", {}),
            )
        )
        return duration_ms

    def mark(
        self,
        name: str,
        category: str,
        input_text: str = "",
        output_text: str = "",
        duration_ms: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        nodes, flows = _category_topology(category, kwargs.get("extra_nodes"))
        self.events.append(
            LatencyEvent(
                name=name,
                category=category,
                at_ms=self._elapsed_ms(),
                duration_ms=round(duration_ms, 1) if duration_ms is not None else None,
                input=input_text,
                output=output_text,
                nodes=nodes,
                flows=flows,
                breakdown=kwargs.get("breakdown", {}),
                user_says=kwargs.get("user_says"),
                agent_says=kwargs.get("agent_says"),
                meta=kwargs.get("meta", {}),
            )
        )

    def on_user_transcript(self, text: str, finished: bool) -> None:
        if not text.strip():
            return
        if finished:
            self._turn += 1
            self._user_turn_end_ms = self._elapsed_ms()
            self._awaiting_agent_audio = True
            self.mark(
                f"user_turn_{self._turn}",
                "client",
                input_text="User speech (16kHz PCM stream)",
                output_text=text.strip(),
                user_says=text.strip(),
                extra_nodes=["user", "voicejs", "ws", "geminiLive", "gemini"],
            )
        else:
            for ev in reversed(self.events):
                if ev.name == f"user_turn_{self._turn}" and ev.user_says:
                    ev.user_says = text.strip()
                    ev.output = text.strip()
                    break

    def on_agent_transcript(self, text: str, finished: bool) -> None:
        if not text.strip():
            return
        name = f"agent_turn_{self._turn or 1}"
        existing = next((e for e in reversed(self.events) if e.name == name), None)
        if existing:
            existing.agent_says = text.strip()
            existing.output = text.strip()
        else:
            self.mark(
                name,
                "gemini",
                output_text=text.strip(),
                agent_says=text.strip(),
            )
        if finished and "TABLE-" in text.upper():
            import re

            m = re.search(r"TABLE-[A-Z0-9]{3}", text.upper())
            if m:
                self.reservation_code = m.group(0)
                self.outcome = "book_new"

    def on_first_agent_audio_after_wait(self) -> None:
        if not self._awaiting_agent_audio:
            return
        ref = self._tool_turn_end_ms or self._user_turn_end_ms
        if ref is None:
            return
        ttfb = self._elapsed_ms() - ref
        self._awaiting_agent_audio = False
        self._tool_turn_end_ms = None
        label = f"gemini_ttfb_turn_{self._turn or 1}"
        self.mark(
            label,
            "gemini",
            input_text="User utterance or tool result",
            output_text=f"First audio chunk ({round(ttfb, 1)} ms after prior step)",
            duration_ms=ttfb,
            breakdown={
                "gemini_inference_ms": round(ttfb, 1),
                "note": "Time from end of user speech / tool response to first agent audio",
            },
        )

    def on_tool_call(
        self,
        name: str,
        args: dict,
        duration_ms: float,
        breakdown: dict[str, float],
        result_summary: str,
    ) -> None:
        self._tool_turn_end_ms = self._elapsed_ms()
        self._awaiting_agent_audio = True
        if name == "book_new" and breakdown.get("success"):
            self.outcome = "book_new"
        elif name == "cancel_reservation":
            self.outcome = "cancel_reservation"
        elif name == "reschedule_reservation":
            self.outcome = "reschedule_reservation"
        elif name == "check_availability":
            self.outcome = self.outcome or "check_availability"

        self.mark(
            f"tool_{name}",
            "tool" if name != "book_new" else "integration",
            input_text=f'{name}({", ".join(f"{k}={v!r}" for k, v in args.items())})',
            output_text=result_summary[:500],
            duration_ms=duration_ms,
            breakdown=breakdown,
            extra_nodes=["gemini", "tools", "booking", "json"]
            + (["calendar", "sheets"] if name == "book_new" else []),
        )

    def merge_client_report(self, report: dict) -> None:
        self.client_events = report.get("events", [])
        for item in self.client_events:
            nodes, flows = _category_topology(
                item.get("category", "client"), item.get("nodes")
            )
            self.events.append(
                LatencyEvent(
                    name=item.get("name", "client_event"),
                    category=item.get("category", "client"),
                    at_ms=float(item.get("at_ms", self._elapsed_ms())),
                    duration_ms=item.get("duration_ms"),
                    input=item.get("input", ""),
                    output=item.get("output", ""),
                    nodes=nodes,
                    flows=flows,
                    breakdown=item.get("breakdown", {}),
                    user_says=item.get("user_says"),
                    agent_says=item.get("agent_says"),
                )
            )

    def finalize(self) -> dict:
        self.events.sort(key=lambda e: e.at_ms)
        total_ms = round(self._elapsed_ms(), 1)
        steps = _build_steps(self.events)
        summary = _build_summary(self.events, total_ms)

        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "total_ms": total_ms,
            "outcome": self.outcome,
            "reservation_code": self.reservation_code,
            "steps": steps,
            "summary": summary,
            "event_count": len(self.events),
        }


def _category_topology(
    category: str, extra_nodes: Optional[list[str]] = None
) -> tuple[list[str], list[str]]:
    nodes = list(extra_nodes or NODE_MAP.get(category, NODE_MAP["server"]))
    flows = []
    for i in range(len(nodes) - 1):
        flows.append(f"{nodes[i]}-{nodes[i + 1]}")
    return nodes, flows


def _build_summary(events: list[LatencyEvent], total_ms: float) -> dict:
    buckets = {
        "client_ms": 0.0,
        "network_ms": 0.0,
        "server_ms": 0.0,
        "gemini_ms": 0.0,
        "tool_ms": 0.0,
        "integration_ms": 0.0,
        "storage_ms": 0.0,
    }
    cat_key = {
        "client": "client_ms",
        "network": "network_ms",
        "server": "server_ms",
        "gemini": "gemini_ms",
        "tool": "tool_ms",
        "integration": "integration_ms",
        "storage": "storage_ms",
    }
    for ev in events:
        if ev.duration_ms is None:
            continue
        key = cat_key.get(ev.category, "server_ms")
        buckets[key] += ev.duration_ms
        for sub_ms in ev.breakdown.values():
            if isinstance(sub_ms, (int, float)):
                pass  # sub-breakdowns are subsets of parent duration

    accounted = sum(buckets.values())
    buckets["unattributed_ms"] = round(max(0, total_ms - accounted), 1)
    for k in buckets:
        buckets[k] = round(buckets[k], 1)
    buckets["total_ms"] = total_ms
    return buckets


def _build_steps(events: list[LatencyEvent]) -> list[dict]:
    steps = []
    for i, ev in enumerate(events):
        steps.append(
            {
                "index": i + 1,
                "title": _human_title(ev.name),
                "desc": _human_desc(ev),
                "category": ev.category,
                "nodes": ev.nodes,
                "flows": ev.flows,
                "input": ev.input or "—",
                "output": ev.output or "—",
                "duration_ms": ev.duration_ms,
                "at_ms": round(ev.at_ms, 1),
                "breakdown": ev.breakdown,
                "userSays": ev.user_says,
                "agentSays": ev.agent_says,
            }
        )
    return steps


def _human_title(name: str) -> str:
    titles = {
        "ws_accept": "WebSocket accepted",
        "gemini_wss_connect": "Connect to Gemini Live (WSS)",
        "gemini_setup": "Gemini session setup",
        "session_ready": "Session ready — mic streaming",
        "client_mic_permission": "Microphone permission",
        "client_ws_open": "Browser WebSocket open",
        "client_session_start": "User starts call",
    }
    if name in titles:
        return titles[name]
    if name.startswith("user_turn_"):
        return f"User speaks (turn {name.split('_')[-1]})"
    if name.startswith("agent_turn_"):
        return f"Agent responds (turn {name.split('_')[-1]})"
    if name.startswith("gemini_ttfb_turn_"):
        return f"Gemini time-to-first-audio (turn {name.split('_')[-1]})"
    if name.startswith("tool_"):
        return f"Tool call: {name.replace('tool_', '')}"
    return name.replace("_", " ").title()


def _human_desc(ev: LatencyEvent) -> str:
    if ev.category == "gemini" and ev.name.startswith("gemini_ttfb"):
        return (
            "Latency from end of user speech (or tool result) until the first "
            "agent audio chunk arrives — dominated by Gemini inference + TTS."
        )
    if ev.category == "tool":
        return "Server-side tool execution on gemini_live.py — no round-trip to browser."
    if ev.category == "integration":
        return "Booking + Google Calendar hold + Sheets log (or mock integrations)."
    if ev.name == "gemini_wss_connect":
        return "TLS handshake and WSS connection to Google generativelanguage.googleapis.com."
    if ev.name == "gemini_setup":
        return "Sending SYSTEM_PROMPT, tools, and VAD config; waiting for setupComplete."
    return f"Measured {ev.category} phase of the voice pipeline."


class LatencyStore:
    """Thread-safe ring buffer of recent voice sessions."""

    def __init__(self, max_sessions: int = 20) -> None:
        self._sessions: list[dict] = []
        self._max = max_sessions
        self._lock = threading.Lock()
        self._active: dict[str, SessionLatencyTracker] = {}

    def create_tracker(self) -> SessionLatencyTracker:
        tracker = SessionLatencyTracker()
        with self._lock:
            self._active[tracker.session_id] = tracker
        return tracker

    def get_tracker(self, session_id: str) -> Optional[SessionLatencyTracker]:
        with self._lock:
            return self._active.get(session_id)

    def finalize_tracker(self, session_id: str) -> Optional[dict]:
        with self._lock:
            tracker = self._active.pop(session_id, None)
        if not tracker:
            return None
        session = tracker.finalize()
        with self._lock:
            self._sessions.insert(0, session)
            self._sessions = self._sessions[: self._max]
        return session

    def latest(self) -> Optional[dict]:
        with self._lock:
            return self._sessions[0] if self._sessions else None

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "session_id": s["session_id"],
                    "started_at": s["started_at"],
                    "total_ms": s["total_ms"],
                    "outcome": s.get("outcome"),
                    "reservation_code": s.get("reservation_code"),
                    "step_count": len(s.get("steps", [])),
                }
                for s in self._sessions
            ]

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._lock:
            for s in self._sessions:
                if s["session_id"] == session_id:
                    return s
        return None


_store: Optional[LatencyStore] = None


def get_latency_store() -> LatencyStore:
    global _store
    if _store is None:
        _store = LatencyStore()
    return _store
