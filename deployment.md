# Shiv Sagar Voice Agent — Vercel Deployment Plan

> **Document version:** 2.1  
> **Last updated:** July 2026  
> **Target platform:** [Vercel](https://vercel.com) — frontend **and** backend on one project

---

## 1. Executive Summary

This project deploys **entirely on Vercel** as a single full-stack application:

| Layer | How it runs on Vercel |
|-------|------------------------|
| **Frontend** | Static UI in `public/` (CDN) — `index.html`, architecture, latency pages |
| **Backend** | FastAPI (`src/server/app.py`) as a Vercel Function |
| **Voice WebSocket** | `/ws/voice` — native WebSocket support on Vercel Functions (Fluid compute) |
| **REST APIs** | `/api/*`, `/health`, etc. — same FastAPI app |

**Same origin in production** — the browser loads the UI and connects to `wss://your-app.vercel.app/ws/voice` with no CORS or split-domain setup.

### Repo files added for Vercel

| File | Purpose |
|------|---------|
| `vercel.json` | Build command, function `maxDuration`, rewrites |
| `pyproject.toml` | FastAPI entrypoint: `src.server.app:app` |
| `scripts/vercel-build.sh` | Copies `src/server/static/` → `public/` |
| `.vercelignore` | Excludes secrets and local-only files from deploy |

---

## 2. Architecture on Vercel

```mermaid
flowchart TB
    subgraph Browser["User browser"]
        UI[Heritage Tech UI]
        MIC[Microphone]
        SPK[Speaker]
    end

    subgraph Vercel["Vercel (single project)"]
        CDN[public/ — CDN static files]
        FN[FastAPI Vercel Function]
        WS[/ws/voice WebSocket]
        API[/api/* REST]
    end

    subgraph Google["Google Cloud"]
        GEMINI[Gemini Live API]
        GCAL[Calendar]
        GSHEET[Sheets]
    end

  subgraph Store["Persistence"]
        TMP[(RESERVATIONS_DATA_DIR)]
        REDIS[(Vercel KV / Redis — optional)]
    end

    Browser --> CDN
    Browser -->|WSS same origin| WS
    WS <-->|audio + tools| GEMINI
    API --> GCAL
    API --> GSHEET
    FN --> TMP
    FN -.-> REDIS
```

**Request routing:**

| URL | Handler |
|-----|---------|
| `/` | `public/index.html` (CDN) |
| `/architecture` | rewrite → `public/architecture.html` |
| `/latency` | rewrite → `public/latency.html` |
| `/static/*` | `public/static/*` (CDN) |
| `/ws/voice` | FastAPI WebSocket |
| `/api/*`, `/health` | FastAPI routes |

---

## 3. Vercel Requirements

| Requirement | Plan | Notes |
|-------------|------|-------|
| **WebSocket voice sessions** | Pro recommended | Up to **800s** function duration configured in `vercel.json` |
| **Fluid compute** | Default (2025+) | Required for WebSockets — enabled on new projects |
| **Python runtime** | 3.9+ | Matches `requirements.txt` |
| **Gemini API key** | Any | Set as Vercel env var |
| **Google auth** | Service account | `GOOGLE_CREDENTIALS_JSON` on Vercel; `GOOGLE_SERVICE_ACCOUNT_PATH` locally |

> **Hobby plan:** Function duration is capped lower (~60s). Voice calls longer than that may disconnect. Use **Vercel Pro** for production voice reservations.

---

## 4. Deployment Phases

### Phase 1 — Prepare repository

- [ ] Push to GitHub (do **not** commit `.env`, service account JSON, `credentials.json`, or `token.json`)
- [ ] Confirm `vercel.json`, `pyproject.toml`, and `scripts/vercel-build.sh` are in the repo
- [ ] Run build locally: `bash scripts/vercel-build.sh` → check `public/` is created

### Phase 2 — Google Cloud setup

- [ ] Enable **Google Calendar API** and **Google Sheets API**
- [ ] Create a **service account** and download the JSON key (Section 8 — recommended)
- [ ] Share your **Google Calendar** with the service account email (Editor)
- [ ] Share your **Google Spreadsheet** with the service account email (Editor)
- [ ] Set `GOOGLE_CALENDAR_ID` to the shared calendar ID (not always `primary` for service accounts)
- [ ] Set `GOOGLE_SHEETS_SPREADSHEET_ID` and `GOOGLE_SHEETS_SHEET_NAME` (e.g. `Sheet1`)
- [ ] For local dev: place JSON in project root and set `GOOGLE_SERVICE_ACCOUNT_PATH` in `.env`

### Phase 3 — Deploy to Vercel

- [ ] Import GitHub repo at [vercel.com/new](https://vercel.com/new)
- [ ] Framework: **FastAPI** (auto-detected) or **Other**
- [ ] Add all environment variables (Section 6)
- [ ] Deploy → note production URL

### Phase 4 — Verify

- [ ] `GET /health` → `200`
- [ ] `GET /api/integrations/status` → calendar + sheets `ok: true`
- [ ] `GET /api/voice/test-gemini` → `ok: true`
- [ ] Open site → **Start Call** → complete test booking
- [ ] Confirm Google Sheet row + Calendar event

### Phase 5 — Production hardening (optional)

- [ ] Add **Vercel KV** or **Upstash Redis** for reservation persistence (Section 7)
- [ ] Custom domain (e.g. `reservations.shivsagar.in`)
- [ ] Enable Vercel Analytics / monitoring

---

## 5. Step-by-Step: Deploy to Vercel

### 5.1 Via Vercel Dashboard

1. Go to [vercel.com/new](https://vercel.com/new) and import your GitHub repository.
2. **Project settings** (usually auto-detected):
   - **Framework Preset:** FastAPI
   - **Build Command:** `bash scripts/vercel-build.sh` (from `vercel.json`)
   - **Install Command:** `pip install -r requirements.txt`
3. **Environment Variables** — add every variable from Section 6 for **Production** (and Preview if desired).
4. Click **Deploy**.
5. When complete, open `https://<project>.vercel.app`.

### 5.2 Via Vercel CLI

```bash
npm i -g vercel
cd "Restaurant voice agent"
vercel login
vercel link
vercel env pull .env.vercel.local   # optional: inspect pulled vars
vercel --prod
```

### 5.3 Custom domain

1. Vercel project → **Settings → Domains**
2. Add your domain (e.g. `reservations.shivsagar.in`)
3. Add DNS CNAME → `cname.vercel-dns.com`
4. HTTPS is automatic

---

## 6. Environment Variables

### 6.1 Local development (`.env`)

Copy `.env.example` to `.env` and configure:

```bash
# Gemini
GEMINI_API_KEY=your_key_here

# Google — service account file (recommended)
GOOGLE_SERVICE_ACCOUNT_PATH=your-service-account.json
GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SHEETS_SHEET_NAME=Sheet1
MOCK_GOOGLE_INTEGRATIONS=false
```

**Example** (this project):

```bash
GOOGLE_SERVICE_ACCOUNT_PATH=heroic-rain-498708-e2-11eb4738512b.json
```

Place the downloaded JSON key in the project root. It is listed in `.gitignore` — never commit it.

Verify locally:

```bash
curl -s http://localhost:8000/api/integrations/status
# → calendar.ok: true, sheets.ok: true
```

### 6.2 Vercel (Production dashboard)

Set under **Project → Settings → Environment Variables**:

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `GEMINI_API_KEY` | ✅ | From [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_LIVE_MODEL` | Optional | `gemini-2.5-flash-native-audio-preview-12-2025` |
| `GEMINI_VOICE` | Optional | `Aoede` |
| `RESTAURANT_TIMEZONE` | Optional | `Asia/Kolkata` |
| `MOCK_GOOGLE_INTEGRATIONS` | Optional | `false` in production |
| `GOOGLE_CREDENTIALS_JSON` | ✅ | Full service account JSON as **one line** (see Section 8) |
| `GOOGLE_CALENDAR_ID` | ✅ | Shared calendar ID (e.g. `...@group.calendar.google.com`) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | ✅ | Spreadsheet ID from URL |
| `GOOGLE_SHEETS_SHEET_NAME` | ✅ | `Sheet1` (must match real tab name) |
| `RESERVATIONS_DATA_DIR` | Recommended | `/tmp/data` on Vercel (ephemeral) |

**Do not set** `GOOGLE_SERVICE_ACCOUNT_PATH` on Vercel — file paths are not available. Use `GOOGLE_CREDENTIALS_JSON` instead.

#### Optional fallbacks (not needed if using service account)

| Variable | Use case |
|----------|----------|
| `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` + `GOOGLE_REFRESH_TOKEN` | Legacy OAuth refresh flow |

### 6.3 Credential priority (`google_auth.py`)

The app resolves Google credentials in this order:

1. `MOCK_GOOGLE_INTEGRATIONS=true` → skip Google APIs
2. `GOOGLE_SERVICE_ACCOUNT_PATH` → load JSON file from disk (**local / Vercel with mounted file — rare**)
3. `GOOGLE_CREDENTIALS_JSON` → parse inline JSON (**Vercel production**)
4. `GOOGLE_REFRESH_TOKEN` + client ID/secret → OAuth refresh
5. `credentials.json` + `token.json` → desktop OAuth (local dev only)

**Never commit** service account JSON, `credentials.json`, `token.json`, or `.env` to git.

---

## 7. Persistent Storage on Vercel

Vercel Functions use an **ephemeral filesystem**. `data/reservations.json` is not durable across deploys or cold starts.

### Short-term (included)

Set in Vercel env:

```
RESERVATIONS_DATA_DIR=/tmp/data
```

Reservations work within a single function instance but may reset on redeploy.

### Production (recommended)

| Option | Setup |
|--------|--------|
| **[Vercel KV](https://vercel.com/docs/storage/vercel-kv)** | Marketplace → add KV → store reservations as JSON blobs |
| **[Upstash Redis](https://vercel.com/marketplace/upstash)** | Shared state across function instances |
| **Supabase / Postgres** | Replace `ReservationService` file store with DB |

For multi-instance WebSocket scaling, Redis/KV is also used for shared session state if you scale beyond one region.

---

## 8. Google Service Account Setup

Service accounts are the **recommended** auth method for both local dev and Vercel production.

### Step 1 — Create service account

1. [Google Cloud Console](https://console.cloud.google.com/) → **IAM & Admin → Service Accounts**
2. **Create service account** (e.g. `restaurant@your-project.iam.gserviceaccount.com`)
3. **Keys → Add key → JSON** → download the file
4. Save in project root (e.g. `heroic-rain-498708-e2-11eb4738512b.json`)

### Step 2 — Enable APIs

Enable in the same Cloud project:

- [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
- [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)

### Step 3 — Share resources with the service account

The service account email looks like:

```
restaurant@heroic-rain-498708-e2.iam.gserviceaccount.com
```

| Resource | How to share |
|----------|----------------|
| **Calendar** | Google Calendar → Settings → Share with service account email → **Make changes to events** |
| **Spreadsheet** | Google Sheets → Share → add service account email → **Editor** |

Copy the **Calendar ID** from calendar settings into `GOOGLE_CALENDAR_ID`. For a shared group calendar, use the ID ending in `@group.calendar.google.com` — not `primary`.

### Step 4 — Configure locally

In `.env`:

```bash
GOOGLE_SERVICE_ACCOUNT_PATH=heroic-rain-498708-e2-11eb4738512b.json
GOOGLE_CALENDAR_ID=a2823967f67ae9eaf53c63747018b17083d1abab63ea033f8eeda9274e340ad3@group.calendar.google.com
GOOGLE_SHEETS_SPREADSHEET_ID=1K9fgoSrfJ3IPqAHlquvkpNTZCbzKk2MWdEroV3_cT7k
GOOGLE_SHEETS_SHEET_NAME=Sheet1
MOCK_GOOGLE_INTEGRATIONS=false
```

Restart the server: `python main.py`

### Step 5 — Configure on Vercel

File paths do not work on Vercel. Paste the **entire** service account JSON into one env var:

1. Open the JSON key file in a text editor
2. Minify to a single line (remove newlines in the private key block is handled by JSON)
3. Vercel → **Settings → Environment Variables** → add:

```
GOOGLE_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...","client_email":"restaurant@....iam.gserviceaccount.com",...}
```

4. Also set `GOOGLE_CALENDAR_ID`, `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SHEETS_SHEET_NAME`
5. Redeploy

**Tip:** In terminal, generate a one-liner for copy-paste:

```bash
python3 -c "import json; print(json.dumps(json.load(open('heroic-rain-498708-e2-11eb4738512b.json'))))"
```

Paste the output as the value of `GOOGLE_CREDENTIALS_JSON` in Vercel.

### Legacy Option — OAuth refresh token

Only if you cannot use a service account:

1. Run locally with `credentials.json` → complete browser OAuth → `token.json` created
2. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` on Vercel

Service account is simpler for server deployments and does not expire like user OAuth tokens.

---

## 9. How the Build Works

```bash
# Runs on every Vercel deploy (vercel.json buildCommand)
bash scripts/vercel-build.sh
```

1. Deletes and recreates `public/`
2. Copies HTML pages to `public/`
3. Copies CSS/JS to `public/static/`
4. Vercel serves `public/**` from the CDN
5. FastAPI handles `/api/*`, `/ws/voice`, `/health`

**Local development** is unchanged:

```bash
python main.py   # http://localhost:8000
```

---

## 10. `vercel.json` Reference

```json
{
  "buildCommand": "bash scripts/vercel-build.sh",
  "functions": {
    "src/server/app.py": {
      "maxDuration": 800
    }
  },
  "rewrites": [
    { "source": "/architecture", "destination": "/architecture.html" },
    { "source": "/latency", "destination": "/latency.html" }
  ]
}
```

- **`maxDuration: 800`** — allows voice calls up to ~13 minutes on Pro. Adjust per your plan limits.
- **Rewrites** — clean URLs for architecture and latency pages.

---

## 11. Pre-Deploy Checklist

| # | Check |
|---|-------|
| 1 | `GEMINI_API_KEY` set in Vercel |
| 2 | Google Calendar + Sheets APIs enabled |
| 3 | `GOOGLE_SHEETS_SHEET_NAME` matches real tab (`Sheet1`) |
| 4 | Service account JSON **not** in git (see `.gitignore`) |
| 5 | Calendar + Sheet shared with service account email |
| 6 | `GOOGLE_SERVICE_ACCOUNT_PATH` set locally **or** `GOOGLE_CREDENTIALS_JSON` on Vercel |
| 7 | `GOOGLE_CALENDAR_ID` is the shared calendar ID (not `primary` unless shared) |
| 8 | `MOCK_GOOGLE_INTEGRATIONS=false` |
| 9 | `RESERVATIONS_DATA_DIR=/tmp/data` set on Vercel |
| 10 | Vercel Pro for voice calls > 60s |
| 11 | `bash scripts/vercel-build.sh` succeeds locally |

---

## 12. Post-Deploy Verification

Replace `YOUR_APP` with your Vercel URL:

```bash
# Health
curl -s https://YOUR_APP.vercel.app/health

# Gemini
curl -s https://YOUR_APP.vercel.app/api/voice/test-gemini

# Google integrations
curl -s https://YOUR_APP.vercel.app/api/integrations/status

# Frontend
curl -sI https://YOUR_APP.vercel.app/
```

**Manual test:** Open the site → **Start Voice Reservation** → speak through a full booking → verify Sheet + Calendar.

---

## 13. CI/CD

| Event | Result |
|-------|--------|
| Push to `main` | Production deploy (UI + API) |
| Pull request | Preview deployment with unique URL |
| `vercel --prod` | CLI production deploy |

Preview deployments use the same FastAPI + WebSocket stack. Set Preview env vars in Vercel if previews need their own `GEMINI_API_KEY`.

---

## 14. Cost Estimate (Monthly)

| Item | Tier | Approx. |
|------|------|---------|
| Vercel Pro | Recommended for voice | ~$20/mo per seat |
| Vercel Function usage | Fluid compute | Pay per active CPU time during voice calls |
| Vercel KV (optional) | Hobby | Free tier available |
| Gemini API | Pay-per-use | By voice minutes |
| Google APIs | Quota | Free within limits |

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Voice stuck on "Connecting…" | `GEMINI_API_KEY` missing | Set in Vercel env, redeploy |
| WebSocket closes mid-call | Function timeout | Upgrade to Pro; confirm `maxDuration: 800` |
| 404 on `/` | Build failed | Check deploy logs; run `scripts/vercel-build.sh` |
| Sheets append fails | Wrong tab name | Set `GOOGLE_SHEETS_SHEET_NAME=Sheet1` |
| Calendar 403 | Calendar API not enabled | Enable in Google Cloud Console |
| Google auth fails | Missing service account config | Local: `GOOGLE_SERVICE_ACCOUNT_PATH`; Vercel: `GOOGLE_CREDENTIALS_JSON` |
| Calendar 404 / forbidden | Calendar not shared | Share calendar with `...@iam.gserviceaccount.com` |
| Sheets permission denied | Sheet not shared | Share spreadsheet with service account (Editor) |
| Reservations disappear | Ephemeral `/tmp` | Add Vercel KV / Redis (Section 7) |
| Static assets 404 | `public/static` missing | Re-run build script; redeploy |

---

## 16. Local vs Vercel

| Concern | Local (`python main.py`) | Vercel |
|---------|--------------------------|--------|
| UI | `src/server/static/` via FastAPI | `public/` via CDN |
| WebSocket | `ws://localhost:8000/ws/voice` | `wss://<app>.vercel.app/ws/voice` |
| Google auth | `GOOGLE_SERVICE_ACCOUNT_PATH` → JSON file | `GOOGLE_CREDENTIALS_JSON` env var |
| Reservations | `data/reservations.json` | `RESERVATIONS_DATA_DIR=/tmp/data` |
| Hot reload | `RELOAD=true` | N/A |

---

## 17. What Stays Local Only

| Component | Reason |
|-----------|--------|
| `mcp/restaurant_mcp_server.py` | Cursor / Claude Desktop MCP — not a web deploy |
| `*-*.json` service account keys | Secrets — use `.gitignore`; on Vercel use `GOOGLE_CREDENTIALS_JSON` |
| `credentials.json` / `token.json` | Legacy OAuth — superseded by service account |

---

## 18. Related Docs

- [implementation.md](implementation.md) — architecture and API reference
- [README.md](README.md) — local quick start
- [.env.example](.env.example) — environment variable template
- [Vercel FastAPI docs](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel WebSockets](https://vercel.com/docs/functions/websockets)

---

## 19. Summary

| Component | Platform |
|-----------|----------|
| Frontend (UI) | **Vercel CDN** (`public/`) |
| Backend (FastAPI) | **Vercel Function** (`src/server/app.py`) |
| Voice WebSocket | **Vercel** (`/ws/voice`, Fluid compute) |
| Google Calendar + Sheets | **Service account** — file locally, `GOOGLE_CREDENTIALS_JSON` on Vercel |
| Reservation storage | `/tmp/data` short-term → **Vercel KV** for production |

**Deploy flow:** Push to GitHub → import on Vercel → set env vars → deploy → test voice booking end-to-end.
