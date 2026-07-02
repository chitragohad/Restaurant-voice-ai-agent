# Shiv Sagar — Restaurant Voice Reservation Agent

A privacy-first voice agent for table bookings at Shiv Sagar. Callers book, reschedule, or cancel without sharing phone, email, or names — they receive a **Reservation Code** (e.g. `TABLE-B99`) to use on arrival.

For architecture, phased rollout, API reference, and troubleshooting, see **[implementation.md](implementation.md)**.  
For production deployment on Vercel (frontend + backend), see **[deployment.md](deployment.md)**.

## Features

| Intent | Description |
|--------|-------------|
| `book_new` | Greet → occasion → time → offer slot/alternatives → confirm → code + calendar + sheet |
| `check_availability` | Check mock inventory for a preferred IST slot |
| `reschedule_reservation` | Move booking by reservation code |
| `cancel_reservation` | Cancel by reservation code |

### On confirm (book_new)
1. Generates unique code (`TABLE-XXX`)
2. **Google Calendar** — tentative hold: `Dining Hold — {Occasion} — {Code}`
3. **Google Sheets** — appends to **Daily Reservation Log**
4. Tells caller: 15-minute hold, full date/time in **IST**

### Voice UX (Gemini Live API)
- **Interruption handling** — barge-in when caller speaks (`START_OF_ACTIVITY_INTERRUPTS`)
- **Noise reduction** — browser echo cancellation + noise suppression on mic capture
- **No PII** — reservation code only
- **Refusals** — no medical/nutrition advice; menu/hours → [shivsagar.in](https://shivsagar.in)

## Quick start

### 1. Install

```bash
cd "Restaurant voice agent"
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure `.env`

```bash
GEMINI_API_KEY=your_key_here   # https://aistudio.google.com/apikey
MOCK_GOOGLE_INTEGRATIONS=true   # set false when Google is configured
```

### 3. Run the web voice UI

```bash
python main.py
```

Open **http://localhost:8000** → tap **Start Call** → speak.

### 4. (Optional) Google Calendar & Sheets

1. Create a [Google Cloud project](https://console.cloud.google.com/)
2. Enable **Google Calendar API** and **Google Sheets API**
3. Create OAuth 2.0 Desktop credentials → save as `credentials.json` in project root
4. Set in `.env`:
   ```bash
   MOCK_GOOGLE_INTEGRATIONS=false
   GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
   GOOGLE_SHEETS_SHEET_NAME=Daily Reservation Log
   ```
5. First run opens browser for OAuth → creates `token.json`

Create a sheet named **Daily Reservation Log** with columns:
`Logged At (IST) | Action | Date | Occasion | Slot (IST) | Code`

### 5. MCP server (Cursor / Claude Desktop)

Add to your MCP config:

```json
{
  "mcpServers": {
    "shiv-sagar-restaurant": {
      "command": "python",
      "args": ["/absolute/path/to/Restaurant voice agent/mcp/restaurant_mcp_server.py"]
    }
  }
}
```

Tools exposed: `book_new`, `cancel_reservation`, `reschedule_reservation`, `check_availability`, `calendar_create_hold`, `calendar_delete_hold`, `sheets_append_reservation`.

## REST API

| Endpoint | Method | Body |
|----------|--------|------|
| `/api/check-availability` | POST | `{ "occasion", "preferred_datetime" }` |
| `/api/book` | POST | `{ "occasion", "date", "time" }` |
| `/api/cancel` | POST | `{ "code" }` |
| `/api/reschedule` | POST | `{ "code", "new_date", "new_time" }` |
| `/ws/voice` | WebSocket | Gemini Live voice session (browser) |
| `/api/realtime/execute-tool` | POST | Execute booking tool via REST |

## Project structure

```
├── main.py                    # Start FastAPI server
├── mcp/
│   └── restaurant_mcp_server.py
├── src/
│   ├── agent/                 # Prompts, tools, voice config
│   ├── booking/               # Mock inventory, codes, reservations
│   ├── integrations/          # Google Calendar & Sheets
│   └── server/                # FastAPI + web voice UI
└── data/
    └── reservations.json      # Local reservation store
```

## Dining occasions

- Standard Dining
- Large Group (6+)
- Outdoor/Patio
- Special Occasion/Anniversary
- Bar/Lounge

## Mock inventory

Lunch slots: 12:00–15:00 IST · Dinner: 18:30–22:00 IST. Capacity varies by occasion. If the preferred slot is taken, the agent offers the **two nearest available slots** in IST.

## CLI voice (alternative)

```bash
python -m src.agent.cli
```

Requires microphone, `GEMINI_API_KEY`, and Python 3.10+ with `pip install google-genai`.
