/**
 * Latency Explorer — real voice session timing visualizer
 */

const NODES = {
  user:       { label: "Caller",            sub: "Browser / Mic",        type: "client" },
  voicejs:    { label: "voice.js",          sub: "PCM capture",          type: "client" },
  ws:         { label: "/ws/voice",         sub: "WebSocket",            type: "server" },
  geminiLive: { label: "gemini_live.py",    sub: "WSS bridge",           type: "server" },
  gemini:     { label: "Gemini Live API",   sub: "Inference + TTS",    type: "gemini" },
  tools:      { label: "gemini_tools.py",   sub: "Tool execution",       type: "tools" },
  booking:    { label: "ReservationService",sub: "inventory + CRUD",     type: "storage" },
  json:       { label: "reservations.json", sub: "Persistence",          type: "storage" },
  calendar:   { label: "Google Calendar",   sub: "Tentative hold",       type: "google" },
  sheets:     { label: "Google Sheets",     sub: "Daily Log",            type: "google" },
};

const NODE_POS = {
  user:       { x: 30,  y: 200, w: 110, h: 52 },
  voicejs:    { x: 170, y: 120, w: 110, h: 52 },
  ws:         { x: 310, y: 60,  w: 110, h: 52 },
  geminiLive: { x: 450, y: 60,  w: 120, h: 52 },
  gemini:     { x: 610, y: 120, w: 120, h: 52 },
  tools:      { x: 450, y: 360, w: 120, h: 52 },
  booking:    { x: 280, y: 420, w: 130, h: 52 },
  json:       { x: 80,  y: 420, w: 130, h: 52 },
  calendar:   { x: 450, y: 460, w: 120, h: 44 },
  sheets:     { x: 610, y: 460, w: 120, h: 44 },
};

const FLOW_EDGES = [
  ["user","voicejs"],["voicejs","ws"],["ws","geminiLive"],["geminiLive","gemini"],
  ["geminiLive","tools"],["tools","booking"],["booking","json"],
  ["booking","calendar"],["booking","sheets"],
  ["gemini","user"],["geminiLive","ws"],["ws","voicejs"],["voicejs","user"],
  ["gemini","geminiLive"],["tools","geminiLive"],
];

let sessionData = null;
let currentStep = 0;
let playTimer = null;
let isPlaying = false;

function edgeId(a, b) { return `${a}-${b}`; }

function center(pos) {
  return { x: pos.x + pos.w / 2, y: pos.y + pos.h / 2 };
}

function curvePath(x1, y1, x2, y2) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = Math.abs(x2 - x1);
  const dy = Math.abs(y2 - y1);
  if (dx > dy) return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
}

function buildDiagramSVG() {
  const svg = document.getElementById("diagram");
  if (!svg) return;
  svg.innerHTML = "";

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `<marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" class="flow-arrow"/></marker>`;
  svg.appendChild(defs);

  const gFlows = document.createElementNS("http://www.w3.org/2000/svg", "g");
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

    const lat = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lat.classList.add("lat-badge");
    lat.id = `lat-${id}`;
    lat.setAttribute("x", pos.x + pos.w / 2);
    lat.setAttribute("y", pos.y - 6);
    lat.setAttribute("text-anchor", "middle");
    lat.textContent = "";
    g.appendChild(lat);

    gNodes.appendChild(g);
  });
  svg.appendChild(gNodes);
}

function formatMs(ms) {
  if (ms == null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function renderSummary(summary, session) {
  const bar = document.getElementById("summary-bar");
  if (!bar) return;

  const items = [
    { lbl: "Total session", val: formatMs(session.total_ms), cls: "" },
    { lbl: "Client", val: formatMs(summary.client_ms), cls: "cat-client" },
    { lbl: "Network", val: formatMs(summary.network_ms), cls: "cat-network" },
    { lbl: "Gemini", val: formatMs(summary.gemini_ms), cls: "cat-gemini" },
    { lbl: "Tools", val: formatMs(summary.tool_ms), cls: "cat-tool" },
    { lbl: "Integrations", val: formatMs(summary.integration_ms), cls: "cat-integration" },
    { lbl: "Unattributed", val: formatMs(summary.unattributed_ms), cls: "" },
  ];

  bar.innerHTML = items.map((i) => `
    <div class="summary-card ${i.cls}">
      <div class="val">${i.val}</div>
      <div class="lbl">${i.lbl}</div>
    </div>`).join("");

  renderWaterfall(summary, session.total_ms);
}

function renderWaterfall(summary, total) {
  const el = document.getElementById("waterfall-bars");
  if (!el || !total) return;

  const cats = [
    ["client", summary.client_ms],
    ["network", summary.network_ms],
    ["server", summary.server_ms],
    ["gemini", summary.gemini_ms],
    ["tool", summary.tool_ms],
    ["integration", summary.integration_ms],
  ].filter(([, v]) => v > 0);

  const max = Math.max(...cats.map(([, v]) => v), 1);

  el.innerHTML = cats.map(([cat, ms]) => {
    const pct = (ms / max) * 100;
    return `<div class="wf-row">
      <span class="wf-label">${cat}</span>
      <div class="wf-track"><div class="wf-fill ${cat}" style="width:${pct}%"></div></div>
      <span class="wf-ms">${formatMs(ms)}</span>
    </div>`;
  }).join("");
}

function renderMeta(session) {
  const meta = document.getElementById("session-meta");
  if (!meta) return;
  const started = session.started_at ? new Date(session.started_at).toLocaleString() : "—";
  meta.innerHTML = `
    <strong>Session</strong> <code>${session.session_id}</code> ·
    <strong>Started</strong> ${started} ·
    <strong>Outcome</strong> ${session.outcome || "voice session"} ·
    ${session.reservation_code ? `<strong>Code</strong> <code>${session.reservation_code}</code>` : ""}`;
}

function renderStep() {
  if (!sessionData?.steps?.length) return;

  const steps = sessionData.steps;
  const step = steps[currentStep];
  const total = steps.length;

  document.getElementById("step-num").textContent = currentStep + 1;
  document.getElementById("step-total").textContent = total;
  document.getElementById("step-title").innerHTML =
    `${step.title}<span class="category-pill ${step.category}">${step.category}</span>`;
  document.getElementById("step-desc").textContent = step.desc || "";
  document.getElementById("io-input").textContent = step.input || "—";
  document.getElementById("io-output").textContent = step.output || "—";

  const durEl = document.getElementById("duration-pill");
  if (step.duration_ms != null) {
    durEl.textContent = `⏱ ${formatMs(step.duration_ms)}`;
    durEl.classList.remove("hidden");
  } else if (step.at_ms != null) {
    durEl.textContent = `@ ${formatMs(step.at_ms)} into session`;
    durEl.classList.remove("hidden");
  } else {
    durEl.classList.add("hidden");
  }

  document.getElementById("btn-prev").disabled = currentStep === 0;
  document.getElementById("btn-next").disabled = currentStep === total - 1;
  document.getElementById("progress-fill").style.width = `${((currentStep + 1) / total) * 100}%`;

  document.querySelectorAll(".node-group").forEach((el) => {
    const id = el.id.replace("node-", "");
    const active = (step.nodes || []).includes(id);
    el.classList.toggle("active", active);
    el.classList.toggle("dim", !active);
  });

  document.querySelectorAll(".flow-path").forEach((el) => el.classList.remove("active"));
  (step.flows || []).forEach((f) => {
    const el = document.getElementById(`flow-${f}`);
    if (el) el.classList.add("active");
  });

  // Node cumulative latency badges
  const nodeTotals = {};
  steps.slice(0, currentStep + 1).forEach((s) => {
    if (!s.duration_ms) return;
    (s.nodes || []).forEach((n) => {
      nodeTotals[n] = (nodeTotals[n] || 0) + s.duration_ms;
    });
  });
  Object.keys(NODE_POS).forEach((id) => {
    const badge = document.getElementById(`lat-${id}`);
    if (badge) badge.textContent = nodeTotals[id] ? formatMs(nodeTotals[id]) : "";
  });

  const breakdownEl = document.getElementById("breakdown-list");
  const bd = step.breakdown || {};
  const keys = Object.keys(bd).filter((k) => typeof bd[k] === "number");
  if (keys.length) {
    breakdownEl.classList.remove("hidden");
    breakdownEl.innerHTML = `<h4>Sub-breakdown</h4>` +
      keys.map((k) => `<div class="breakdown-row"><span>${k.replace(/_/g, " ")}</span><span>${formatMs(bd[k])}</span></div>`).join("");
  } else {
    breakdownEl.classList.add("hidden");
    breakdownEl.innerHTML = "";
  }

  const thread = document.getElementById("dialogue-thread");
  thread.innerHTML = "";
  for (let i = 0; i <= currentStep; i++) {
    const s = steps[i];
    if (s.userSays) thread.appendChild(utterance("user", "Caller", s.userSays, i === currentStep));
    if (s.agentSays) thread.appendChild(utterance("agent", "Voice Agent", s.agentSays, i === currentStep));
  }
  if (!thread.children.length) {
    thread.innerHTML = `<p style="color:var(--text-dim);font-size:0.85rem;font-style:italic">No speech in this step — advance to see conversation.</p>`;
  }
  thread.scrollTop = thread.scrollHeight;
}

function utterance(role, speaker, text, current) {
  const div = document.createElement("div");
  div.className = `utterance ${role}${current ? " current" : ""}`;
  div.innerHTML = `<div class="speaker">${speaker}</div>${escapeHtml(text)}`;
  return div;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function showContent() {
  document.getElementById("empty-state")?.classList.add("hidden");
  document.getElementById("latency-content")?.classList.remove("hidden");
}

function showEmpty(sessions) {
  document.getElementById("empty-state")?.classList.remove("hidden");
  document.getElementById("latency-content")?.classList.add("hidden");

  const list = document.getElementById("session-list");
  if (!list) return;
  if (!sessions?.length) {
    list.innerHTML = "";
    return;
  }
  list.innerHTML = `<p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:0.5rem">Or pick a recent session:</p>` +
    sessions.map((s) => `
      <button class="session-opt" data-id="${s.session_id}">
        ${s.session_id} · ${formatMs(s.total_ms)} · ${s.outcome || "session"} ${s.reservation_code ? `· ${s.reservation_code}` : ""}
      </button>`).join("");

  list.querySelectorAll(".session-opt").forEach((btn) => {
    btn.addEventListener("click", () => loadSession(btn.dataset.id));
  });
}

async function loadSession(sessionId) {
  const url = sessionId
    ? `/api/latency/sessions/${sessionId}`
    : "/api/latency/latest";

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const listRes = await fetch("/api/latency/sessions");
      const list = await listRes.json();
      showEmpty(list.sessions || []);
      return;
    }
    sessionData = await res.json();
    if (!sessionData?.steps?.length) {
      const listRes = await fetch("/api/latency/sessions");
      const list = await listRes.json();
      showEmpty(list.sessions || []);
      return;
    }

    currentStep = 0;
    showContent();
    buildDiagramSVG();
    renderMeta(sessionData);
    renderSummary(sessionData.summary || {}, sessionData);
    renderStep();

    const u = new URL(location.href);
    u.searchParams.set("session", sessionData.session_id);
    history.replaceState(null, "", u);
  } catch (err) {
    console.error(err);
    showEmpty([]);
  }
}

function nextStep() {
  if (!sessionData || currentStep >= sessionData.steps.length - 1) { stopPlay(); return; }
  currentStep++;
  renderStep();
}

function prevStep() {
  if (currentStep > 0) { currentStep--; renderStep(); }
}

function stopPlay() {
  isPlaying = false;
  if (playTimer) { clearInterval(playTimer); playTimer = null; }
  const btn = document.getElementById("btn-play");
  if (btn) { btn.textContent = "▶ Play Flow"; btn.classList.remove("playing"); }
}

function togglePlay() {
  if (isPlaying) { stopPlay(); return; }
  isPlaying = true;
  const btn = document.getElementById("btn-play");
  btn.textContent = "⏸ Pause";
  btn.classList.add("playing");

  if (currentStep === sessionData.steps.length - 1) {
    currentStep = 0;
    renderStep();
  }

  playTimer = setInterval(() => {
    if (currentStep < sessionData.steps.length - 1) {
      currentStep++;
      renderStep();
    } else {
      stopPlay();
    }
  }, 2200);
}

function init() {
  document.getElementById("btn-next")?.addEventListener("click", () => { stopPlay(); nextStep(); });
  document.getElementById("btn-prev")?.addEventListener("click", () => { stopPlay(); prevStep(); });
  document.getElementById("btn-play")?.addEventListener("click", togglePlay);
  document.getElementById("btn-reset")?.addEventListener("click", () => { stopPlay(); currentStep = 0; renderStep(); });
  document.getElementById("btn-refresh")?.addEventListener("click", () => {
    const id = new URLSearchParams(location.search).get("session");
    loadSession(id);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { stopPlay(); nextStep(); }
    if (e.key === "ArrowLeft") { stopPlay(); prevStep(); }
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
  });

  const sessionId = new URLSearchParams(location.search).get("session");
  loadSession(sessionId);
}

document.addEventListener("DOMContentLoaded", init);
