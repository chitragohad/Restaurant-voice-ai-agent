# Shiv Sagar Voice Reservation Agent — Implementation Plan

> **Document version:** 1.0  
> **Last updated:** July 2026  
> **Stack:** Python 3.9+ · FastAPI · Gemini Live API · Google Calendar & Sheets · Heritage Tech UI

---

## 1. Executive Summary

The Shiv Sagar Voice Reservation Agent is a **privacy-first, voice-driven table booking system** for a premium North Indian restaurant. Callers book, reschedule, or cancel tables **without sharing phone numbers, email, or names**. The only identifier is a **Reservation Code** (e.g. `TABLE-B99`), shown on arrival.

The system combines:

- A **Gemini Live** voice agent (real-time audio, barge-in, tool calling)
- A **mock table inventory** engine with occasion-based capacity
- **Google Calendar** tentative holds and **Google Sheets** kitchen logs (via MCP-compatible integrations)
- A **Heritage Tech** desktop web UI (Stitch design system)

**Who it helps**

| Stakeholder | Benefit |
|-------------|---------|
| Diners | Frictionless hold in seconds; no forms or PII |
| Restaurant managers | Compliant pre-booking without manual data entry |
| Kitchen / floor staff | Calendar holds + Daily Reservation Log |

---

## 2. Goals & Constraints

### 2.1 Functional goals

| # | Goal | Status |
|---|------|--------|
| G1 | Voice booking with 5 intents: `book_new`, `check_availability`, `reschedule_reservation`, `cancel_reservation` | ✅ Implemented |
| G2 | Offer exact slot or two nearest alternatives (mock inventory) | ✅ Implemented |
| G3 | Generate unique `TABLE-XXX` reservation codes | ✅ Implemented |
| G4 | On confirm: Calendar hold + Sheets log | ✅ Implemented |
| G5 | 15-minute hold messaging; all times in IST | ✅ Implemented |
| G6 | Reschedule / cancel by code only | ✅ Implemented |

### 2.2 Non-functional constraints

| Constraint | Implementation |
|------------|----------------|
| **Privacy first** | No PII collected; code-only identity enforced in `SYSTEM_PROMPT` |
| **IST clarity** | Agent always states IST; UI shows IST badge |
| **Overflow** | No slots → clear message + offer another day |
| **Refusals** | No medical/nutrition advice; redirect to shivsagar.in for menu/hours |
| **Interruptions** | Gemini `START_OF_ACTIVITY_INTERRUPTS` + client audio stop |
| **Noisy environments** | Browser `echoCancellation`, `noiseSuppression`, `autoGainControl` |

---

## 3. System Architecture

```mermaid
flowchart TB
    subgraph Browser["Browser (Heritage Tech UI)"]
        UI[index.html + heritage.css]
        VJS[voice.js]
        MIC[Microphone 16kHz PCM]
        SPK[Speaker 24kHz PCM]
    end

    subgraph Server["FastAPI Server :8000"]
        APP[app.py]
        WS[/ws/voice WebSocket]
        GL[gemini_live.py]
        RS[ReservationService]
        TOOLS[gemini_tools.py]
        INT[integrations/]
    end

    subgraph Gemini["Google Gemini Live API"]
        LIVE[WSS BidiGenerateContent]
        VAD[Semantic VAD + Barge-in]
    end

    subgraph Google["Google Workspace"]
        CAL[Calendar API]
        SHEET[Sheets API]
    end

    subgraph Storage["Local"]
        JSON[(data/reservations.json)]
    end

    UI --> VJS
    VJS -->|WebSocket audio + events| WS
    WS --> GL
    GL -->|WSS proxy| LIVE
    LIVE -->|toolCall| GL
    GL --> TOOLS --> RS
    RS --> JSON
    TOOLS --> INT
    INT --> CAL
    INT --> SHEET
    VJS --> MIC
    SPK --> VJS
    APP -->|REST| RS
```

### 3.1 Request paths

| Path | Protocol | Purpose |
|------|----------|---------|
| `/` | HTTP | Desktop homepage + voice panel |
| `/ws/voice` | WebSocket | Browser ↔ Gemini Live bridge |
| `/api/book` | REST POST | Programmatic booking |
| `/api/check-availability` | REST POST | Slot lookup |
| `/api/cancel` | REST POST | Cancel by code |
| `/api/reschedule` | REST POST | Reschedule by code |
| `/api/voice/status` | REST GET | Voice config health check |
| MCP stdio | MCP | Cursor/Claude tool access |

---

## 4. Implementation Phases

### Phase 1 — Core booking engine ✅

**Objective:** Reservation logic independent of voice.

| Task | File(s) | Deliverable |
|------|---------|-------------|
| Mock slot inventory by occasion | `src/booking/inventory.py` | Lunch/dinner slots, per-occasion capacity |
| Reservation code generator | `src/booking/codes.py` | `TABLE-XXX` format |
| CRUD + persistence | `src/booking/reservations.py` | JSON store in `data/reservations.json` |
| Unit tests | `tests/test_booking.py` | Availability, book, cancel flows |

**Acceptance criteria**

- `check_availability` returns exact match or 2 nearest slots
- `book_new` decrements inventory; `cancel` releases slot
- Codes are unique and persisted across restarts

---

### Phase 2 — Google integrations ✅

**Objective:** Calendar holds and kitchen log on confirm.

| Task | File(s) | Deliverable |
|------|---------|-------------|
| OAuth helper | `src/integrations/google_auth.py` | `credentials.json` → `token.json` |
| Calendar tentative holds | `src/integrations/calendar.py` | `Dining Hold — {Occasion} — {Code}` |
| Sheets append | `src/integrations/sheets.py` | Daily Reservation Log rows |
| Orchestration | `src/integrations/booking_actions.py` | Book/cancel/reschedule lifecycle |

**Acceptance criteria**

- `MOCK_GOOGLE_INTEGRATIONS=true` logs without API calls
- Real mode creates calendar event + sheet row on `book_new`
- Cancel removes calendar hold and logs `CANCELLED`

**Sheet columns**

```
Logged At (IST) | Action | Date | Occasion | Slot (IST) | Code
```

---

### Phase 3 — Voice agent (Gemini Live) ✅

**Objective:** Real-time voice with tool execution.

| Task | File(s) | Deliverable |
|------|---------|-------------|
| System prompt & guardrails | `src/agent/prompts.py` | Conversation flow, refusals, IST rules |
| Tool declarations | `src/agent/gemini_tools.py` | 4 function schemas + execution |
| WebSocket bridge | `src/server/gemini_live.py` | Browser ↔ Gemini proxy |
| Browser client | `src/server/static/voice.js` | Mic capture, playback, UI states |

**Voice session flow**

```
1. User clicks Start Call
2. Browser requests mic permission
3. WebSocket opens → server connects to Gemini Live
4. Server sends setup (prompt + tools + VAD config)
5. Gemini sends setupComplete → UI shows "Listening"
6. User speaks → 16kHz PCM → server → Gemini
7. Gemini may call tool → server executes → toolResponse → Gemini continues
8. Gemini audio 24kHz PCM → server → browser playback
9. User interrupts → barge-in → playback stops
```

**UI states (Heritage Tech)**

| State | Mic | Status color | Visual |
|-------|-----|--------------|--------|
| Idle | Gold | Muted | Placeholder transcript |
| Connecting | Gold + ring | Gold | "Requesting microphone…" |
| Listening | Red End Call | Green | Waveform + live transcript |
| Speaking | Red | Gold | Agent audio playing |
| Success | Overlay | Green | `TABLE-XXX` code card |
| Error | Gold | Red | Actionable message |

---

### Phase 4 — Frontend (Heritage Tech) ✅

**Objective:** Desktop UI per Stitch design system.

| Task | File(s) | Deliverable |
|------|---------|-------------|
| Design tokens | `stitch_.../heritage_tech/DESIGN.md` | Colors, typography, spacing |
| Self-contained CSS | `src/server/static/heritage.css` | No CDN dependency |
| Homepage + voice panel | `src/server/static/index.html` | Hero, how-it-works, manage booking |
| Inline SVG icons | `index.html` sprite | No Material Symbols font dependency |

**Design reference**

- Primary: `#FFC66B` / `#E8A838` (saffron gold)
- Background: `#0F1419` (midnight)
- Surface cards: `#1A2332` (slate navy)
- Listening: `#4ADE80` (soft emerald)
- Fonts: Cormorant Garamond (display), Plus Jakarta Sans (headlines), DM Sans (body), JetBrains Mono (codes)

---

### Phase 5 — MCP server ✅

**Objective:** Expose booking + Google tools to Cursor/Claude Desktop.

| Task | File(s) | Deliverable |
|------|---------|-------------|
| MCP stdio server | `mcp/restaurant_mcp_server.py` | 7 tools |
| Cursor config | `.cursor/mcp.json` | Local dev wiring |

**MCP tools:** `book_new`, `cancel_reservation`, `reschedule_reservation`, `check_availability`, `calendar_create_hold`, `calendar_delete_hold`, `sheets_append_reservation`

> Requires Python 3.10+ and `pip install mcp`

---

### Phase 6 — Hardening & ops (recommended next)

| Task | Priority | Notes |
|------|----------|-------|
| Ephemeral Gemini tokens (no API key in server WS URL) | High | Production security |
| PostgreSQL / Redis for reservations | Medium | Replace JSON file |
| Rate limiting on `/ws/voice` | Medium | Abuse prevention |
| Structured logging + metrics | Medium | Datadog / Cloud Logging |
| Telephony (Twilio/LiveKit) | Low | Phone-in bookings |
| Hindi / multilingual voice | Low | Gemini Live supports 70+ languages |
| Admin dashboard for managers | Low | View Daily Reservation Log in-app |

---

## 5. Component Reference

### 5.1 Booking layer (`src/booking/`)

```
inventory.py     → SlotInventory, DiningOccasion, TimeSlot
codes.py         → generate_reservation_code()
reservations.py  → ReservationService (singleton via get_reservation_service())
```

**Dining occasions**

- `standard_dining` — capacity 8/slot
- `large_group_6_plus` — capacity 3/slot
- `outdoor_patio` — capacity 4/slot
- `special_occasion` — capacity 2/slot
- `bar_lounge` — capacity 6/slot

**Slot times (IST)**

- Lunch: 12:00, 12:30, 13:00, 13:30, 14:00, 14:30, 15:00
- Dinner: 18:30, 19:00, 19:30, 20:00, 20:30, 21:00, 21:30, 22:00

### 5.2 Agent layer (`src/agent/`)

```
prompts.py       → SYSTEM_PROMPT (conversation policy)
gemini_tools.py  → Function declarations + execute_booking_tool()
voice_agent.py   → Gemini config helpers
cli.py           → Optional CLI (google-genai, Python 3.10+)
```

### 5.3 Server layer (`src/server/`)

```
app.py           → FastAPI routes, static mount
gemini_live.py   → WebSocket bridge to Gemini Live
static/          → index.html, heritage.css, voice.js
```

### 5.4 Integrations (`src/integrations/`)

```
google_auth.py      → OAuth2 desktop flow
calendar.py         → Tentative holds
sheets.py           → Daily Reservation Log append
booking_actions.py  → Lifecycle orchestration
```

---

## 6. Conversation Flow (Voice Agent)

### 6.1 Book new

```
Greet
  → Ask dining occasion (5 options)
  → Ask preferred day/time (IST)
  → check_availability tool
  → If exact match: offer slot
  → If not: offer two nearest alternatives
  → Wait for explicit confirmation
  → book_new tool
  → Speak: code, date/time (IST), 15-min hold, wish great day
```

### 6.2 Reschedule

```
Ask Reservation Code only
  → Ask new date/time (IST)
  → check_availability
  → Confirm
  → reschedule_reservation tool
```

### 6.3 Cancel

```
Ask Reservation Code only
  → Confirm cancellation intent
  → cancel_reservation tool
```

### 6.4 Check availability only

```
Occasion + preferred time
  → check_availability
  → Report results (no booking unless confirmed)
```

---

## 7. Environment Configuration

Copy `.env.example` to `.env` (never commit `.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes (voice) | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_LIVE_MODEL` | No | Default: `gemini-2.5-flash-native-audio-preview-12-2025` |
| `GEMINI_VOICE` | No | Default: `Aoede` (Puck, Charon, Kore, Fenrir also available) |
| `RESTAURANT_TIMEZONE` | No | `Asia/Kolkata` |
| `MOCK_GOOGLE_INTEGRATIONS` | No | `true` for demos without Google OAuth |
| `GOOGLE_CREDENTIALS_PATH` | If Google live | Path to OAuth `credentials.json` |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | If Google live | Target spreadsheet ID |
| `GOOGLE_SHEETS_SHEET_NAME` | No | Default: `Daily Reservation Log` |
| `GOOGLE_CALENDAR_ID` | No | Default: `primary` |
| `HOST` / `PORT` | No | Default: `0.0.0.0:8000` |

---

## 8. Setup & Runbook

### 8.1 Local development

```bash
cd "Restaurant voice agent"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY
python main.py
```

Open **http://localhost:8000** → **Start Call**.

### 8.2 Google OAuth (first time)

1. Enable Calendar API + Sheets API in Google Cloud Console
2. Create OAuth 2.0 Desktop credential → `credentials.json` in project root
3. Set `MOCK_GOOGLE_INTEGRATIONS=false`
4. First API call opens browser → saves `token.json`

### 8.3 Verify health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/voice/status
python tests/test_booking.py
```

### 8.4 MCP (Cursor)

Configure `.cursor/mcp.json` or user MCP settings to point at `mcp/restaurant_mcp_server.py`.

---

## 9. API Reference

### REST

**Check availability**

```http
POST /api/check-availability
Content-Type: application/json

{
  "occasion": "Standard Dining",
  "preferred_datetime": "2026-07-04 19:00"
}
```

**Book**

```http
POST /api/book
Content-Type: application/json

{
  "occasion": "Standard Dining",
  "date": "2026-07-04",
  "time": "19:00"
}
```

**Cancel**

```http
POST /api/cancel
Content-Type: application/json

{ "code": "TABLE-B99" }
```

**Reschedule**

```http
POST /api/reschedule
Content-Type: application/json

{
  "code": "TABLE-B99",
  "new_date": "2026-07-05",
  "new_time": "20:00"
}
```

### WebSocket (`/ws/voice`)

**Client → Server**

```json
{ "type": "audio", "data": "<base64 PCM 16kHz little-endian>" }
```

**Server → Client**

```json
{ "type": "ready" }
{ "type": "audio", "data": "<base64 PCM 24kHz>" }
{ "type": "transcript", "role": "user|agent", "text": "...", "finished": false }
{ "type": "interrupted" }
{ "type": "turn_complete" }
{ "type": "error", "message": "..." }
```

---

## 10. Project Structure

```
Restaurant voice agent/
├── main.py                          # Uvicorn entrypoint
├── requirements.txt
├── .env.example                     # Template (no secrets)
├── implementation.md                # This document
├── README.md
├── data/
│   └── reservations.json            # Local reservation store
├── mcp/
│   └── restaurant_mcp_server.py     # MCP stdio server
├── stitch_shiv_sagar_voice_system/  # Stitch design exports (reference)
│   └── heritage_tech/DESIGN.md
├── src/
│   ├── agent/
│   │   ├── prompts.py               # SYSTEM_PROMPT
│   │   ├── gemini_tools.py          # Tool schemas + execution
│   │   ├── voice_agent.py
│   │   └── cli.py
│   ├── booking/
│   │   ├── inventory.py
│   │   ├── codes.py
│   │   └── reservations.py
│   ├── integrations/
│   │   ├── google_auth.py
│   │   ├── calendar.py
│   │   ├── sheets.py
│   │   └── booking_actions.py
│   └── server/
│       ├── app.py
│       ├── gemini_live.py
│       └── static/
│           ├── index.html
│           ├── heritage.css
│           └── voice.js
└── tests/
    └── test_booking.py
```

---

## 11. Testing Strategy

| Layer | How | Command / Tool |
|-------|-----|----------------|
| Booking logic | Unit tests | `python tests/test_booking.py` |
| REST API | curl / Postman | `/api/book`, `/api/cancel`, etc. |
| Voice | Manual browser | Start Call → speak booking flow |
| Google integrations | Mock mode first | `MOCK_GOOGLE_INTEGRATIONS=true` |
| MCP | Cursor agent | Invoke `book_new` tool |

**Suggested manual voice test script**

1. "I'd like to book a table for standard dining on Friday at 7 PM"
2. Confirm offered slot
3. Note `TABLE-XXX` code on success overlay
4. "Cancel reservation TABLE-XXX"
5. Ask "Is the butter chicken safe for my severe nut allergy?" → expect refusal + shivsagar.in redirect

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| UI white / broken layout | Cached old Tailwind version | Hard refresh (`Cmd+Shift+R`); ensure `heritage.css?v=2` loads |
| Icons show as text (`mic`, `restaurant`) | Old cached HTML | Hard refresh; SVG sprite is inline in `index.html` |
| WebSocket closes immediately | Missing `GEMINI_API_KEY` | Add key to `.env`, restart server |
| Mic not working | Permission denied | Allow mic in browser; click Start Call on user gesture |
| No agent audio | Gemini model/voice issue | Check `GEMINI_LIVE_MODEL` and API quota |
| Calendar/Sheets not updating | Mock mode or OAuth | Set `MOCK_GOOGLE_INTEGRATIONS=false`, run OAuth flow |
| Port 8000 in use | Stale process | `lsof -ti:8000 \| xargs kill -9` then `python main.py` |

---

## 13. Security Notes

- **Never commit** `.env`, `credentials.json`, or `token.json`
- Gemini API key is currently passed server-side to Google WSS (acceptable for local dev; use ephemeral tokens for production)
- No PII is stored — only reservation codes and slot metadata
- `.gitignore` excludes secrets and virtualenv

---

## 14. Success Metrics

| Metric | Target |
|--------|--------|
| Time to complete booking (voice) | < 90 seconds |
| PII fields collected | 0 |
| IST stated on every confirmation | 100% |
| Calendar + sheet write on confirm | 100% (when Google enabled) |
| Barge-in response | < 500ms perceived stop |

---

## 15. References

- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api)
- [Google Calendar API](https://developers.google.com/workspace/calendar)
- [Google Sheets API](https://developers.google.com/sheets/api)
- Restaurant site: [shivsagar.in](https://shivsagar.in)
- Design system: `stitch_shiv_sagar_voice_system/heritage_tech/DESIGN.md`
