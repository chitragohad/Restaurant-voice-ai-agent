/**
 * Architecture Explorer — interactive flow visualizer
 */

const NODES = {
  user:      { id: "user",      label: "Caller",           sub: "Browser / Mic",       type: "user" },
  voicejs:   { id: "voicejs",   label: "voice.js",         sub: "16kHz PCM capture",   type: "client" },
  ws:        { id: "ws",        label: "/ws/voice",        sub: "WebSocket",           type: "server" },
  geminiLive:{ id: "geminiLive",label: "gemini_live.py",   sub: "WSS bridge",          type: "server" },
  gemini:    { id: "gemini",    label: "Gemini Live API",  sub: "Audio + VAD",         type: "gemini" },
  prompt:    { id: "prompt",    label: "SYSTEM_PROMPT",    sub: "prompts.py",          type: "prompt" },
  tools:     { id: "tools",     label: "gemini_tools.py",  sub: "Tool execution",      type: "tools" },
  booking:   { id: "booking",   label: "ReservationService",sub: "inventory + CRUD",   type: "storage" },
  json:      { id: "json",      label: "reservations.json",sub: "Local persistence",  type: "storage" },
  calendar:  { id: "calendar",  label: "Google Calendar",  sub: "Tentative hold",      type: "google" },
  sheets:    { id: "sheets",    label: "Google Sheets",    sub: "Daily Log",           type: "google" },
  guard:     { id: "guard",     label: "Guardrails",       sub: "Refusals + privacy",  type: "guard" },
};

const SCENARIOS = {
  book: {
    title: "Book a Table",
    intent: "book_new",
    steps: [
      {
        title: "Start voice session",
        desc: "Caller clicks Start Call. Browser requests microphone permission and opens a WebSocket to the server.",
        nodes: ["user", "voicejs", "ws"],
        flows: ["user-voicejs", "voicejs-ws"],
        input: "User click on Start Call button",
        output: 'WebSocket connection to ws://localhost:8000/ws/voice',
        userSays: null,
        agentSays: null,
      },
      {
        title: "Server connects to Gemini Live",
        desc: "FastAPI accepts the WebSocket. gemini_live.py opens a secure connection to Google's BidiGenerateContent endpoint.",
        nodes: ["ws", "geminiLive", "gemini"],
        flows: ["ws-geminiLive", "geminiLive-gemini"],
        input: "Client WebSocket handshake + GEMINI_API_KEY from .env",
        output: "Open WSS to generativelanguage.googleapis.com",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Inject system prompt & tools",
        desc: "The setup message sends SYSTEM_PROMPT (conversation rules, privacy, refusals) and all 4 function declarations to Gemini. This shapes every response.",
        nodes: ["geminiLive", "prompt", "tools", "gemini"],
        flows: ["geminiLive-gemini", "prompt-gemini", "tools-gemini"],
        input: 'setup: { systemInstruction: SYSTEM_PROMPT, tools: [check_availability, book_new, cancel, reschedule], activityHandling: START_OF_ACTIVITY_INTERRUPTS }',
        output: "Gemini session configured with voice (Aoede), VAD, and tool schemas",
        promptNote: "Prompt enforces: no PII, IST times, occasion flow, explicit confirm before book",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Session ready",
        desc: "Gemini sends setupComplete. Server relays { type: 'ready' } to the browser. UI switches to Listening state.",
        nodes: ["gemini", "geminiLive", "voicejs", "user"],
        flows: ["gemini-geminiLive", "geminiLive-ws", "ws-voicejs"],
        input: "setupComplete from Gemini",
        output: '{ "type": "ready" } → voice.js enables mic streaming',
        userSays: null,
        agentSays: null,
      },
      {
        title: "Agent greets caller",
        desc: "Gemini generates opening audio. Transcript streams back. Caller hears the welcome in the browser speaker (24kHz PCM).",
        nodes: ["gemini", "geminiLive", "voicejs", "user", "prompt"],
        flows: ["gemini-geminiLive", "geminiLive-ws", "ws-voicejs", "voicejs-user"],
        input: "Implicit start-of-session (no user audio yet)",
        output: 'Audio PCM 24kHz + transcript: "Namaste! Welcome to Shiv Sagar…"',
        agentSays: "Namaste! Welcome to Shiv Sagar. How may I help you with your reservation today?",
        promptNote: "Prompt step 1: Greet warmly and ask how you can help",
      },
      {
        title: "Caller states booking intent",
        desc: "Microphone captures speech. voice.js encodes 16kHz PCM as base64 and sends over WebSocket. Gemini transcribes and understands intent.",
        nodes: ["user", "voicejs", "ws", "geminiLive", "gemini"],
        flows: ["user-voicejs", "voicejs-ws", "ws-geminiLive", "geminiLive-gemini"],
        input: 'Audio chunks: { "type": "audio", "data": "<base64 PCM 16kHz>" }',
        output: 'Transcript: intent = book_new, occasion = Standard Dining, time = Friday 7 PM',
        userSays: "I'd like to book a table for standard dining this Friday at 7 PM.",
        agentSays: null,
      },
      {
        title: "Agent asks to confirm occasion",
        desc: "Following the prompt flow, Gemini may clarify occasion if needed. Here the caller already stated Standard Dining.",
        nodes: ["gemini", "prompt", "user"],
        flows: ["gemini-user", "prompt-gemini"],
        input: "Parsed user intent + conversation history",
        output: "Agent confirms occasion or asks from the 5 options",
        userSays: null,
        agentSays: "Wonderful — Standard Dining for this Friday. Let me check what's available at 7:00 PM IST.",
        promptNote: "Prompt step 2–3: Confirm occasion, ask preferred day/time (IST)",
      },
      {
        title: "Tool call: check_availability",
        desc: "Gemini decides to call check_availability. Server intercepts toolCall — does NOT send to browser.",
        nodes: ["gemini", "geminiLive", "tools"],
        flows: ["gemini-geminiLive", "geminiLive-tools"],
        input: 'functionCall: { name: "check_availability", args: { occasion: "Standard Dining", preferred_datetime: "2026-07-04 19:00" } }',
        output: "Server routes to execute_booking_tool()",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Query mock inventory",
        desc: "ReservationService checks SlotInventory for the occasion. Returns exact match or two nearest alternatives.",
        nodes: ["tools", "booking", "json"],
        flows: ["tools-booking", "booking-json"],
        input: "occasion=standard_dining, preferred=2026-07-04 19:00 IST",
        output: '{ "available": true, "exact_match": { "date": "2026-07-04", "time": "19:00" }, "alternatives": [] }',
        storageNote: "Reads capacity from in-memory inventory; existing bookings from reservations.json",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Tool response → Gemini",
        desc: "Server sends toolResponse back to Gemini. Agent formulates spoken offer — always stating IST.",
        nodes: ["tools", "geminiLive", "gemini", "user"],
        flows: ["tools-geminiLive", "geminiLive-gemini", "gemini-user"],
        input: 'toolResponse: { result: "Slot available: Friday 4 July 2026 at 7:00 PM IST" }',
        output: "Agent audio + transcript with slot offer",
        agentSays: "I have a table available on Friday, 4 July 2026 at 7:00 PM IST. Shall I confirm this reservation for you?",
        promptNote: "Prompt step 5–6: Offer exact slot; wait for explicit confirmation",
      },
      {
        title: "Caller confirms",
        desc: "User says yes. Gemini detects confirmation. Barge-in enabled if user interrupts mid-sentence.",
        nodes: ["user", "voicejs", "gemini"],
        flows: ["user-voicejs", "voicejs-ws", "ws-geminiLive", "geminiLive-gemini"],
        input: "Audio: affirmative confirmation",
        output: "Intent: proceed with book_new",
        userSays: "Yes, please confirm that.",
        agentSays: null,
      },
      {
        title: "Tool call: book_new",
        desc: "On explicit confirm, Gemini calls book_new. Server executes booking + Google integrations.",
        nodes: ["gemini", "tools", "booking", "calendar", "sheets"],
        flows: ["gemini-tools", "tools-booking", "booking-calendar", "booking-sheets"],
        input: 'functionCall: { name: "book_new", args: { occasion: "Standard Dining", date: "2026-07-04", time: "19:00" } }',
        output: "Reservation created with code TABLE-B99",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Persist & integrate",
        desc: "Three writes happen: JSON file, Calendar tentative hold, Sheets daily log row.",
        nodes: ["booking", "json", "calendar", "sheets"],
        flows: ["booking-json", "booking-calendar", "booking-sheets"],
        input: "New reservation record",
        output: 'JSON: { code: "TABLE-B99", status: "confirmed" }\nCalendar: "Dining Hold — Standard Dining — TABLE-B99"\nSheets: row appended to Daily Reservation Log',
        storageNote: "data/reservations.json · Google Calendar · Google Sheets (or MOCK_GOOGLE_INTEGRATIONS logs only)",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Confirmation to caller",
        desc: "Agent speaks reservation code, full IST datetime, and 15-minute hold policy. UI shows success overlay.",
        nodes: ["gemini", "user", "prompt", "guard"],
        flows: ["gemini-user"],
        input: "book_new success payload",
        output: "Spoken confirmation + UI success state with TABLE-B99",
        agentSays: "You're all set! Your reservation code is TABLE-B99 — that's T-A-B-L-E hyphen B-9-9. Friday, 4 July 2026 at 7:00 PM IST. We'll hold your table for 15 minutes when you arrive. Have a wonderful day!",
        promptNote: "Prompt step 7: Code + IST datetime + 15-min hold + warm close",
        guardNote: "No phone, email, or name was ever collected — privacy by design",
      },
    ],
  },

  reschedule: {
    title: "Update Reservation",
    intent: "reschedule_reservation",
    steps: [
      {
        title: "Active voice session",
        desc: "Caller is already connected. SYSTEM_PROMPT and tools are loaded from session setup.",
        nodes: ["user", "voicejs", "ws", "gemini", "prompt", "tools"],
        flows: ["user-voicejs", "voicejs-ws", "ws-geminiLive", "prompt-gemini"],
        input: "Existing Gemini Live session",
        output: "Ready for reschedule intent",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Caller requests reschedule",
        desc: "User asks to change their booking. Gemini identifies reschedule_reservation intent.",
        nodes: ["user", "gemini", "prompt"],
        flows: ["user-voicejs", "voicejs-ws", "gemini-user"],
        input: "Audio: reschedule request",
        output: "Intent: reschedule_reservation",
        userSays: "I need to change my reservation to Saturday instead.",
        agentSays: null,
        promptNote: "Prompt: Ask for Reservation Code only — never phone or email",
      },
      {
        title: "Agent requests code only",
        desc: "Privacy guardrail: identity is code-only. Agent will not ask for name or contact info.",
        nodes: ["gemini", "guard", "prompt", "user"],
        flows: ["gemini-user", "guard-gemini"],
        input: "Reschedule intent detected",
        output: "Request for TABLE-XXX code",
        agentSays: "Of course. May I have your Reservation Code? For example, TABLE-B99.",
        guardNote: "NEVER ask for phone, email, or full names",
        userSays: null,
      },
      {
        title: "Caller provides code",
        desc: "User speaks their code. Gemini parses TABLE-C42.",
        nodes: ["user", "gemini"],
        flows: ["user-voicejs", "gemini-user"],
        input: "Audio: reservation code",
        output: "code = TABLE-C42",
        userSays: "It's TABLE-C42.",
        agentSays: "Thank you. What new date and time would you prefer, in IST?",
      },
      {
        title: "Check new slot availability",
        desc: "Agent calls check_availability for the new datetime before rescheduling.",
        nodes: ["gemini", "tools", "booking", "json"],
        flows: ["gemini-tools", "tools-booking", "booking-json"],
        input: 'check_availability({ occasion: from existing booking, preferred_datetime: "2026-07-05 20:00" })',
        output: '{ "available": true, "exact_match": { "date": "2026-07-05", "time": "20:00" } }',
        storageNote: "Looks up TABLE-C42 in reservations.json to get occasion",
        userSays: "Saturday at 8 PM please.",
        agentSays: null,
      },
      {
        title: "Offer & confirm new slot",
        desc: "Agent offers Saturday 8 PM IST and waits for explicit confirmation per prompt rules.",
        nodes: ["gemini", "user", "prompt"],
        flows: ["gemini-user"],
        input: "Availability result",
        output: "Spoken offer + wait for confirm",
        agentSays: "Saturday, 5 July 2026 at 8:00 PM IST is available. Shall I move your reservation to that time?",
        promptNote: "Same confirm-before-action rule as new bookings",
        userSays: "Yes, move it please.",
      },
      {
        title: "Tool call: reschedule_reservation",
        desc: "Server updates reservation, releases old slot, books new slot, updates Calendar and Sheets.",
        nodes: ["gemini", "tools", "booking", "json", "calendar", "sheets"],
        flows: ["gemini-tools", "tools-booking", "booking-json", "booking-calendar", "booking-sheets"],
        input: 'reschedule_reservation({ code: "TABLE-C42", new_date: "2026-07-05", new_time: "20:00" })',
        output: "Updated reservation + calendar event moved + sheet row with RESCHEDULED action",
        storageNote: "Old slot returned to inventory; new slot decremented",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Confirmation",
        desc: "Agent confirms new datetime in IST. Code stays the same.",
        nodes: ["gemini", "user", "json"],
        flows: ["gemini-user"],
        input: "Reschedule success",
        output: "Spoken confirmation",
        agentSays: "Done! Your reservation TABLE-C42 is now Saturday, 5 July 2026 at 8:00 PM IST. See you then!",
        userSays: null,
      },
    ],
  },

  cancel: {
    title: "Cancel Reservation",
    intent: "cancel_reservation",
    steps: [
      {
        title: "Active voice session",
        desc: "Caller connected with prompt and tools already in context.",
        nodes: ["user", "gemini", "prompt", "tools"],
        flows: ["user-gemini", "prompt-gemini"],
        input: "Live session",
        output: "Ready",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Caller wants to cancel",
        desc: "User states cancellation intent. Gemini routes to cancel flow.",
        nodes: ["user", "gemini"],
        flows: ["user-voicejs", "gemini-user"],
        input: "Audio: cancel request",
        output: "Intent: cancel_reservation",
        userSays: "I need to cancel my table booking.",
        agentSays: "I'm sorry to hear that. Could you share your Reservation Code?",
      },
      {
        title: "Code-only identification",
        desc: "Privacy guardrail enforced — only TABLE-XXX accepted as identity.",
        nodes: ["gemini", "guard", "prompt"],
        flows: ["guard-gemini", "prompt-gemini"],
        input: "Cancel intent",
        output: "Request code only",
        guardNote: "No PII collection — code is the sole identifier",
        userSays: "TABLE-A17.",
        agentSays: "Just to confirm — you'd like to cancel reservation TABLE-A17?",
      },
      {
        title: "Explicit cancellation confirm",
        desc: "Prompt requires confirming intent before destructive action.",
        nodes: ["gemini", "user", "prompt"],
        flows: ["gemini-user"],
        input: "Code TABLE-A17 provided",
        output: "Awaiting yes/no",
        promptNote: "Prompt: Confirm they want to cancel before calling tool",
        userSays: "Yes, cancel it.",
        agentSays: null,
      },
      {
        title: "Tool call: cancel_reservation",
        desc: "Server cancels booking, frees inventory slot, removes calendar hold, logs cancellation.",
        nodes: ["gemini", "tools", "booking", "json", "calendar", "sheets"],
        flows: ["gemini-tools", "tools-booking", "booking-json", "booking-calendar", "booking-sheets"],
        input: 'cancel_reservation({ code: "TABLE-A17" })',
        output: '{ "success": true, "code": "TABLE-A17", "status": "cancelled" }',
        storageNote: "Slot released in inventory · Calendar hold deleted · Sheets: action=CANCELLED",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Cancellation acknowledged",
        desc: "Agent confirms cancellation warmly. No follow-up PII requested.",
        nodes: ["gemini", "user"],
        flows: ["gemini-user"],
        input: "Cancel success",
        output: "Spoken acknowledgment",
        agentSays: "Your reservation TABLE-A17 has been cancelled. We hope to welcome you to Shiv Sagar another time.",
        userSays: null,
      },
    ],
  },

  menu: {
    title: "Ask About Menu",
    intent: "general_question (redirect)",
    steps: [
      {
        title: "Active voice session",
        desc: "Caller connected. SYSTEM_PROMPT includes refusal and redirect rules for non-booking questions.",
        nodes: ["user", "gemini", "prompt", "guard"],
        flows: ["prompt-gemini", "guard-gemini"],
        input: "Live session with full prompt context",
        output: "Agent ready — booking tools available but not needed",
        promptNote: "Prompt Refusals section loaded at session start",
        userSays: null,
        agentSays: null,
      },
      {
        title: "Caller asks menu question",
        desc: "User asks about food items. This is outside the agent's booking scope.",
        nodes: ["user", "gemini"],
        flows: ["user-voicejs", "gemini-user"],
        input: "Audio: menu / dietary question",
        output: "Classified as general info — not a booking intent",
        userSays: "Do you have butter chicken? And is it very spicy?",
        agentSays: null,
      },
      {
        title: "Guardrail: no menu details",
        desc: "Prompt explicitly forbids discussing menu items in detail. Agent must redirect.",
        nodes: ["gemini", "guard", "prompt"],
        flows: ["guard-gemini", "prompt-gemini"],
        input: "Menu question detected",
        output: "Redirect response — no tool calls made",
        guardNote: "Do NOT discuss menu items in detail → redirect to shivsagar.in",
        promptNote: '"For menu, timings, and other details, please visit shivsagar.in."',
        userSays: null,
        agentSays: null,
      },
      {
        title: "Agent redirects to website",
        desc: "Agent gives the scripted redirect. No data written anywhere — no booking tools invoked.",
        nodes: ["gemini", "user", "guard"],
        flows: ["gemini-user"],
        input: "Guardrail match: general info",
        output: "Spoken redirect — zero storage writes",
        agentSays: "For menu, timings, and other details, please visit shivsagar.in. Is there anything else I can help with for a reservation?",
        userSays: null,
      },
      {
        title: "Medical/allergy refusal (bonus guardrail)",
        desc: "If caller asks about allergies, a stricter refusal applies — no medical advice.",
        nodes: ["user", "gemini", "guard", "prompt"],
        flows: ["user-gemini", "guard-gemini"],
        input: "Audio: allergy safety question",
        output: "Medical refusal script — still no PII, no tools",
        userSays: "I have a severe nut allergy — is the dal safe for me?",
        agentSays: "I'm not able to advise on medical or allergy concerns. Please speak with our staff on arrival or check shivsagar.in for menu details. I can help you book a table if you'd like.",
        guardNote: "Do NOT give medical or nutritional advice",
        promptNote: "Separate refusal path from menu redirect — both block tool usage",
      },
    ],
  },
};

// SVG node positions (viewBox 0 0 900 520)
const NODE_POS = {
  user:       { x: 30,  y: 200, w: 110, h: 52 },
  voicejs:    { x: 170, y: 120, w: 110, h: 52 },
  ws:         { x: 310, y: 60,  w: 110, h: 52 },
  geminiLive: { x: 450, y: 60,  w: 120, h: 52 },
  gemini:     { x: 610, y: 120, w: 120, h: 52 },
  prompt:     { x: 610, y: 280, w: 120, h: 52 },
  tools:      { x: 450, y: 360, w: 120, h: 52 },
  booking:    { x: 280, y: 420, w: 130, h: 52 },
  json:       { x: 80,  y: 420, w: 130, h: 52 },
  calendar:   { x: 450, y: 460, w: 120, h: 44 },
  sheets:     { x: 610, y: 460, w: 120, h: 44 },
  guard:      { x: 760, y: 280, w: 110, h: 52 },
};

const FLOW_EDGES = [
  ["user", "voicejs"], ["voicejs", "ws"], ["ws", "geminiLive"], ["geminiLive", "gemini"],
  ["geminiLive", "tools"], ["tools", "booking"], ["booking", "json"],
  ["booking", "calendar"], ["booking", "sheets"],
  ["prompt", "gemini"], ["tools", "gemini"], ["guard", "gemini"],
  ["gemini", "user"], ["geminiLive", "ws"], ["ws", "voicejs"], ["voicejs", "user"],
  ["gemini", "geminiLive"], ["tools", "geminiLive"], ["guard", "geminiLive"],
];

let currentScenario = "book";
let currentStep = 0;
let playTimer = null;
let isPlaying = false;

function edgeId(a, b) { return `${a}-${b}`; }

function buildDiagramSVG() {
  const svg = document.getElementById("diagram");
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `<marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" class="flow-arrow"/></marker>`;
  svg.appendChild(defs);

  const gFlows = document.createElementNS("http://www.w3.org/2000/svg", "g");
  gFlows.id = "flows-layer";

  FLOW_EDGES.forEach(([a, b]) => {
    const pa = center(NODE_POS[a]);
    const pb = center(NODE_POS[b]);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.id = `flow-${edgeId(a, b)}`;
    path.classList.add("flow-path");
    path.setAttribute("d", curvePath(pa.x, pa.y, pb.x, pb.y));
    path.setAttribute("marker-end", "url(#arrowhead)");
    gFlows.appendChild(path);
  });
  svg.appendChild(gFlows);

  const gNodes = document.createElementNS("http://www.w3.org/2000/svg", "g");
  gNodes.id = "nodes-layer";

  Object.entries(NODE_POS).forEach(([id, pos]) => {
    const n = NODES[id];
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.id = `node-${id}`;
    g.classList.add("node-group", `type-${n.type}`);

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.classList.add("node-rect");
    rect.setAttribute("x", pos.x);
    rect.setAttribute("y", pos.y);
    rect.setAttribute("width", pos.w);
    rect.setAttribute("height", pos.h);
    rect.setAttribute("rx", 8);
    g.appendChild(rect);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.classList.add("node-label");
    label.setAttribute("x", pos.x + pos.w / 2);
    label.setAttribute("y", pos.y + pos.h / 2 - 2);
    label.setAttribute("text-anchor", "middle");
    label.textContent = n.label;
    g.appendChild(label);

    const sub = document.createElementNS("http://www.w3.org/2000/svg", "text");
    sub.classList.add("node-sublabel");
    sub.setAttribute("x", pos.x + pos.w / 2);
    sub.setAttribute("y", pos.y + pos.h / 2 + 12);
    sub.setAttribute("text-anchor", "middle");
    sub.textContent = n.sub;
    g.appendChild(sub);

    gNodes.appendChild(g);
  });
  svg.appendChild(gNodes);
}

function center(pos) {
  return { x: pos.x + pos.w / 2, y: pos.y + pos.h / 2 };
}

function curvePath(x1, y1, x2, y2) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = Math.abs(x2 - x1);
  const dy = Math.abs(y2 - y1);
  if (dx > dy) {
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  }
  return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
}

function renderStep() {
  const scenario = SCENARIOS[currentScenario];
  const step = scenario.steps[currentStep];
  const total = scenario.steps.length;

  document.getElementById("step-num").textContent = currentStep + 1;
  document.getElementById("step-total").textContent = total;
  document.getElementById("step-title").textContent = step.title;
  document.getElementById("step-desc").textContent = step.desc;
  document.getElementById("io-input").textContent = step.input || "—";
  document.getElementById("io-output").textContent = step.output || "—";

  document.getElementById("btn-prev").disabled = currentStep === 0;
  document.getElementById("btn-next").disabled = currentStep === total - 1;

  const pct = ((currentStep + 1) / total) * 100;
  document.getElementById("progress-fill").style.width = `${pct}%`;

  // Highlight nodes
  document.querySelectorAll(".node-group").forEach((el) => {
    const id = el.id.replace("node-", "");
    const active = step.nodes.includes(id);
    el.classList.toggle("active", active);
    el.classList.toggle("dim", !active);
  });

  // Highlight flows
  document.querySelectorAll(".flow-path").forEach((el) => {
    el.classList.remove("active");
  });
  (step.flows || []).forEach((f) => {
    const el = document.getElementById(`flow-${f}`);
    if (el) el.classList.add("active");
  });

  // Badges
  const badges = document.getElementById("badges-row");
  badges.innerHTML = "";
  if (step.guardNote) {
    badges.innerHTML += `<span class="badge badge-guard">🛡 ${step.guardNote}</span>`;
  }
  if (step.storageNote) {
    badges.innerHTML += `<span class="badge badge-storage">💾 ${step.storageNote}</span>`;
  }
  if (step.promptNote) {
    badges.innerHTML += `<span class="badge badge-prompt">✦ Prompt: ${step.promptNote}</span>`;
  }

  // Dialogue — show all utterances up to current step
  const thread = document.getElementById("dialogue-thread");
  thread.innerHTML = "";
  for (let i = 0; i <= currentStep; i++) {
    const s = scenario.steps[i];
    if (s.userSays) {
      thread.appendChild(makeUtterance("user", "Caller", s.userSays, i === currentStep && s.userSays));
    }
    if (s.agentSays) {
      thread.appendChild(makeUtterance("agent", "Voice Agent", s.agentSays, i === currentStep && s.agentSays));
    }
  }
  thread.scrollTop = thread.scrollHeight;
}

function makeUtterance(role, speaker, text, isCurrent) {
  const div = document.createElement("div");
  div.className = `utterance ${role} visible${isCurrent ? " current" : ""}`;
  div.innerHTML = `<div class="speaker">${speaker}</div>${escapeHtml(text)}`;
  return div;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function selectScenario(key) {
  stopPlay();
  currentScenario = key;
  currentStep = 0;
  document.querySelectorAll(".scenario-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.scenario === key);
  });
  renderStep();
}

function nextStep() {
  const total = SCENARIOS[currentScenario].steps.length;
  if (currentStep < total - 1) {
    currentStep++;
    renderStep();
  } else {
    stopPlay();
  }
}

function prevStep() {
  if (currentStep > 0) {
    currentStep--;
    renderStep();
  }
}

function togglePlay() {
  if (isPlaying) {
    stopPlay();
    return;
  }
  isPlaying = true;
  const btn = document.getElementById("btn-play");
  btn.textContent = "⏸ Pause";
  btn.classList.add("playing");

  if (currentStep === SCENARIOS[currentScenario].steps.length - 1) {
    currentStep = 0;
    renderStep();
  }

  playTimer = setInterval(() => {
    const total = SCENARIOS[currentScenario].steps.length;
    if (currentStep < total - 1) {
      currentStep++;
      renderStep();
    } else {
      stopPlay();
    }
  }, 2800);
}

function stopPlay() {
  isPlaying = false;
  if (playTimer) {
    clearInterval(playTimer);
    playTimer = null;
  }
  const btn = document.getElementById("btn-play");
  if (btn) {
    btn.textContent = "▶ Play Flow";
    btn.classList.remove("playing");
  }
}

function init() {
  buildDiagramSVG();

  document.querySelectorAll(".scenario-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectScenario(btn.dataset.scenario));
  });

  document.getElementById("btn-next").addEventListener("click", () => { stopPlay(); nextStep(); });
  document.getElementById("btn-prev").addEventListener("click", () => { stopPlay(); prevStep(); });
  document.getElementById("btn-play").addEventListener("click", togglePlay);
  document.getElementById("btn-reset").addEventListener("click", () => {
    stopPlay();
    currentStep = 0;
    renderStep();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { stopPlay(); nextStep(); }
    if (e.key === "ArrowLeft") { stopPlay(); prevStep(); }
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
  });

  selectScenario("book");
}

document.addEventListener("DOMContentLoaded", init);
