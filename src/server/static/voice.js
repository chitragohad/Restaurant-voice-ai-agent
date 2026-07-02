/**
 * Shiv Sagar voice client — Heritage Tech UI + Gemini Live WebSocket
 */

const INPUT_RATE = 16000;
const OUTPUT_RATE = 24000;

const panel = document.getElementById("voice-panel");
const statusEl = document.getElementById("voice-status");
const transcriptEl = document.getElementById("transcript");
const placeholderEl = document.getElementById("transcript-placeholder");
const micBtn = document.getElementById("micBtn");
const micLabel = document.getElementById("micLabel");
const micIcon = document.getElementById("micIcon");
const micPulse = document.getElementById("mic-pulse");
const loadingRing = document.getElementById("loading-ring");
const waveContainer = document.getElementById("wave-container");
const bargeHint = document.getElementById("barge-hint");
const micHelper = document.getElementById("mic-helper");
const successPanel = document.getElementById("success-panel");
const reservationCodeEl = document.getElementById("reservation-code");
const reservationDetailsEl = document.getElementById("reservation-details");
const heroStartBtn = document.getElementById("hero-start-btn");
const manageStartBtn = document.getElementById("manage-start-btn");
const successDismiss = document.getElementById("success-dismiss");

let ws = null;
let captureContext = null;
let mediaStream = null;
let processor = null;
let silentGain = null;
let player = null;
let active = false;
let sessionReady = false;
let hadError = false;
let agentSpeaking = false;
let turnCompletePending = false;

// Latency tracking (client-side)
let latencyT0 = 0;
let latencySessionId = null;
let latencyClientEvents = [];
let latencyMicStart = 0;
let latencyWsStart = 0;
let redirectToLatency = false;

const latencyLink = document.getElementById("latency-link");

function latPush(name, category, input, output, durationMs, extra = {}) {
  const atMs = latencyT0 ? performance.now() - latencyT0 : 0;
  latencyClientEvents.push({
    name,
    category,
    input: input || "",
    output: output || "",
    duration_ms: durationMs != null ? Math.round(durationMs * 10) / 10 : null,
    at_ms: Math.round(atMs * 10) / 10,
    nodes: extra.nodes,
    user_says: extra.userSays || null,
    agent_says: extra.agentSays || null,
    breakdown: extra.breakdown || {},
  });
}

function flushLatencyReport() {
  if (ws && ws.readyState === WebSocket.OPEN && latencyClientEvents.length) {
    try {
      ws.send(JSON.stringify({ type: "latency_report", events: latencyClientEvents }));
    } catch {
      /* ignore */
    }
  }
}

let readyWaiter = null;

function waitForReady(timeoutMs = 45000) {
  return new Promise((resolve, reject) => {
    readyWaiter = { resolve, reject };
    setTimeout(() => {
      if (readyWaiter) {
        readyWaiter.reject(new Error("Agent setup timeout — server may be busy. Refresh and try again."));
        readyWaiter = null;
      }
    }, timeoutMs);
  });
}

function resolveReady() {
  if (readyWaiter) {
    readyWaiter.resolve();
    readyWaiter = null;
  }
}

function updateLatencyLink() {
  if (!latencyLink) return;
  if (latencySessionId) {
    latencyLink.href = `/latency?session=${latencySessionId}`;
    latencyLink.classList.remove("hidden");
  }
}

function setMicIcon(name) {
  const use = micIcon?.querySelector("use");
  if (use) use.setAttribute("href", name === "end" ? "#icon-call-end" : "#icon-mic");
}

micBtn?.addEventListener("click", () => {
  if (active) stopSession();
  else startSession();
});

heroStartBtn?.addEventListener("click", () => {
  document.getElementById("voice")?.scrollIntoView({ behavior: "smooth" });
  if (!active) startSession();
});

manageStartBtn?.addEventListener("click", () => {
  document.getElementById("voice")?.scrollIntoView({ behavior: "smooth" });
  if (!active) startSession();
});

successDismiss?.addEventListener("click", () => successPanel?.classList.add("hidden"));

reservationCodeEl?.addEventListener("click", () => {
  const code = reservationCodeEl.textContent;
  if (!code || code.includes("—")) return;
  navigator.clipboard?.writeText(code).then(() => {
    const orig = reservationCodeEl.textContent;
    reservationCodeEl.textContent = "COPIED";
    reservationCodeEl.style.color = "var(--green)";
    setTimeout(() => {
      reservationCodeEl.textContent = orig;
      reservationCodeEl.style.color = "";
    }, 2000);
  });
});

function setUiState(state) {
  panel?.classList.remove("voice-state-idle", "voice-state-connecting", "voice-state-listening", "voice-state-speaking", "voice-state-error");
  panel?.classList.add(`voice-state-${state}`);

  micPulse?.classList.add("hidden");
  loadingRing?.classList.add("hidden");
  loadingRing?.classList.remove("loading-red", "loading-listen");
  waveContainer?.classList.add("hidden");
  bargeHint?.classList.add("hidden");
  micHelper?.classList.add("hidden");

  micBtn?.classList.remove("mic-red");
  micLabel?.classList.remove("label-white");

  if (state === "idle" || state === "error") {
    setMicIcon("mic");
    micLabel.textContent = "Start Call";
    placeholderEl?.classList.remove("hidden");
    transcriptEl?.classList.add("hidden");
  }

  if (state === "connecting") {
    setMicIcon("mic");
    micLabel.textContent = "Connecting…";
    loadingRing?.classList.remove("hidden", "loading-red", "loading-listen");
    micHelper?.classList.remove("hidden");
    placeholderEl?.classList.remove("hidden");
    transcriptEl?.classList.add("hidden");
  }

  if (state === "listening" || state === "speaking") {
    micBtn?.classList.add("mic-red");
    setMicIcon("end");
    micLabel.textContent = "End Call";
    micLabel?.classList.add("label-white");
    placeholderEl?.classList.add("hidden");
    transcriptEl?.classList.remove("hidden");
    bargeHint?.classList.remove("hidden");
    micPulse?.classList.remove("hidden");
  }

  if (state === "listening") {
    waveContainer?.classList.remove("hidden");
    loadingRing?.classList.remove("hidden", "loading-red");
    loadingRing?.classList.add("loading-listen");
  }

  if (state === "speaking") {
    loadingRing?.classList.remove("hidden", "loading-listen");
    loadingRing?.classList.add("loading-red");
    waveContainer?.classList.add("hidden");
  }
}

function setStatus(text, tone = "muted") {
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.className = "";
  if (tone === "gold") statusEl.classList.add("status-gold");
  else if (tone === "green") statusEl.classList.add("status-green");
  else if (tone === "error") statusEl.classList.add("status-error");
}

function sanitizeTranscript(text) {
  if (!text) return "";
  return text
    .replace(/<ctrl\d+>/gi, "")
    .replace(/<\/?[a-z][^>]*>/gi, "")
    .replace(/[\u0000-\u001f\u007f-\u009f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function mergeTranscriptText(previous, incoming) {
  const prev = sanitizeTranscript(previous);
  const next = sanitizeTranscript(incoming);
  if (!next) return prev;
  if (!prev) return next;
  if (next === prev) return prev;
  if (next.startsWith(prev)) return next;
  if (prev.startsWith(next)) return prev;
  if (prev.endsWith(next)) return prev;
  const maxOverlap = Math.min(prev.length, next.length);
  for (let i = maxOverlap; i > 0; i--) {
    if (prev.endsWith(next.slice(0, i))) {
      return `${prev}${next.slice(i)}`.replace(/\s+/g, " ").trim();
    }
  }
  return `${prev} ${next}`.replace(/\s+/g, " ").trim();
}

function isMostlyEnglish(text) {
  const letters = [...text].filter((c) => /\p{L}/u.test(c));
  if (!letters.length) return true;
  const latin = letters.filter((c) => c.charCodeAt(0) < 128).length;
  return latin / letters.length >= 0.85;
}

function appendTranscript(role, text, finished = false) {
  text = sanitizeTranscript(text);
  if (!text || !transcriptEl) return;

  const isUser = role === "user";
  if (isUser && !isMostlyEnglish(text)) {
    if (finished) {
      setStatus("Please speak in English for your reservation", "gold");
    }
    return;
  }
  const lines = transcriptEl.querySelectorAll(`[data-role="${role}"]:not([data-finished])`);
  const last = lines[lines.length - 1];

  if (last) {
    const body = last.querySelector(".tx-body");
    if (body) {
      const merged = finished
        ? text
        : mergeTranscriptText(body.dataset.fullText || body.textContent, text);
      body.dataset.fullText = merged;
      body.textContent = merged;
    }
  } else {
    const block = document.createElement("div");
    block.dataset.role = role;
    block.className = `tx-block${isUser ? " user" : ""}`;
    block.innerHTML = `
      <span class="tx-label">${isUser ? "You" : "Agent"}</span>
      <p class="tx-body ${isUser ? "tx-user" : "tx-agent"}"></p>`;
    const body = block.querySelector(".tx-body");
    body.dataset.fullText = text;
    body.textContent = text;
    transcriptEl.appendChild(block);
  }

  if (finished) markTranscriptFinished(role);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;

  if (!isUser) detectReservationSuccess(transcriptEl.querySelector(`[data-role="agent"]:not([data-finished]) .tx-body`)?.textContent || text);
}

function markTranscriptFinished(role) {
  transcriptEl?.querySelectorAll(`[data-role="${role}"]:not([data-finished])`).forEach((el) => {
    el.dataset.finished = "1";
  });
}

function detectReservationSuccess(text) {
  const codeMatch = text.match(/TABLE-[A-Z0-9]{3}/i);
  if (!codeMatch) return;

  reservationCodeEl.textContent = codeMatch[0].toUpperCase();
  const details = [];
  if (/standard dining/i.test(text)) details.push("<p><strong>Occasion</strong><br/>Standard Dining</p>");
  if (/large group/i.test(text)) details.push("<p><strong>Occasion</strong><br/>Large Group (6+)</p>");
  if (/patio|outdoor/i.test(text)) details.push("<p><strong>Occasion</strong><br/>Outdoor/Patio</p>");
  if (/special occasion|anniversary/i.test(text)) details.push("<p><strong>Occasion</strong><br/>Special Occasion</p>");
  if (/bar|lounge/i.test(text)) details.push("<p><strong>Occasion</strong><br/>Bar/Lounge</p>");

  const istMatch = text.match(/(\w+day,?\s+\d{1,2}\s+\w+\s+\d{4}[^.]*IST)/i);
  if (istMatch) details.push(`<p><strong>When</strong><br/>${istMatch[1]}</p>`);
  details.push("<p style='color:var(--text-muted);font-size:13px'>Table held for 15 minutes from reservation time.</p>");

  reservationDetailsEl.innerHTML = details.join("");
  successPanel?.classList.remove("hidden");
  updateLatencyLink();
  redirectToLatency = true;
}

const PCM_WORKLET_SRC = URL.createObjectURL(
  new Blob(
    [
      `class PcmRingProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunks = [];
    this.offset = 0;
    this.hadAudio = false;
    this.silenceFrames = 0;
    this.port.onmessage = (e) => {
      if (e.data.type === "chunk") {
        this.chunks.push(e.data.samples);
        this.hadAudio = true;
        this.silenceFrames = 0;
      } else if (e.data.type === "clear") {
        this.chunks = [];
        this.offset = 0;
        this.hadAudio = false;
        this.silenceFrames = 0;
        this.port.postMessage({ type: "idle" });
      }
    };
  }
  process(inputs, outputs) {
    const out = outputs[0][0];
    let i = 0;
    while (i < out.length) {
      if (!this.chunks.length) {
        out.fill(0, i);
        break;
      }
      const cur = this.chunks[0];
      const avail = cur.length - this.offset;
      const take = Math.min(avail, out.length - i);
      out.set(cur.subarray(this.offset, this.offset + take), i);
      this.offset += take;
      i += take;
      if (this.offset >= cur.length) {
        this.chunks.shift();
        this.offset = 0;
      }
    }
    if (this.chunks.length) {
      this.silenceFrames = 0;
    } else if (this.hadAudio) {
      this.silenceFrames += 1;
      if (this.silenceFrames > 24) {
        this.hadAudio = false;
        this.silenceFrames = 0;
        this.port.postMessage({ type: "idle" });
      }
    }
    return true;
  }
}
registerProcessor("pcm-ring", PcmRingProcessor);`,
    ],
    { type: "application/javascript" },
  ),
);

class PcmPlayer {
  constructor(sourceSampleRate) {
    this.sourceSampleRate = sourceSampleRate;
    this.ctx = null;
    this.gain = null;
    this.node = null;
    this.useWorklet = false;
    this.workletReady = false;
    this.playing = false;
    this.onDrainCallback = null;
    // Fallback scheduler state
    this.queue = [];
    this.sources = [];
    this.nextTime = 0;
  }

  async init() {
    if (this.ctx) return;
    this.ctx = new AudioContext({ latencyHint: "playback" });
    this.gain = this.ctx.createGain();
    this.gain.gain.value = 0.92;
    this.gain.connect(this.ctx.destination);
    if (this.ctx.state === "suspended") await this.ctx.resume();

    try {
      await this.ctx.audioWorklet.addModule(PCM_WORKLET_SRC);
      this.node = new AudioWorkletNode(this.ctx, "pcm-ring", {
        outputChannelCount: [1],
      });
      this.node.port.onmessage = (e) => {
        if (e.data.type === "idle") {
          this.playing = false;
          this._finishDrain();
        }
      };
      this.node.connect(this.gain);
      this.useWorklet = true;
    } catch (err) {
      console.warn("AudioWorklet unavailable, using scheduled buffers", err);
      this.useWorklet = false;
    }
    this.workletReady = true;
  }

  isPlaying() {
    if (this.useWorklet) return this.playing;
    return this.playing || this.queue.length > 0 || this.sources.length > 0;
  }

  whenIdle(callback) {
    if (!this.isPlaying()) {
      callback();
      return;
    }
    this.onDrainCallback = callback;
  }

  _decodePcm16Base64(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const sampleCount = Math.floor(bytes.length / 2);
    const floats = new Float32Array(sampleCount);
    for (let i = 0; i < sampleCount; i++) {
      const lo = bytes[i * 2];
      const hi = bytes[i * 2 + 1];
      let sample = lo | (hi << 8);
      if (sample >= 0x8000) sample -= 0x10000;
      floats[i] = sample / 32768;
    }
    return floats;
  }

  resample(floats, fromRate, toRate) {
    if (fromRate === toRate) return floats;
    const ratio = fromRate / toRate;
    const outLen = Math.max(1, Math.round(floats.length / ratio));
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * ratio;
      const idx = Math.floor(srcIdx);
      const frac = srcIdx - idx;
      const s0 = floats[idx] || 0;
      const s1 = floats[Math.min(idx + 1, floats.length - 1)];
      out[i] = s0 + frac * (s1 - s0);
    }
    return out;
  }

  interrupt() {
    this.playing = false;
    this.onDrainCallback = null;
    if (this.useWorklet && this.node) {
      this.node.port.postMessage({ type: "clear" });
    }
    this.sources.forEach((s) => {
      try { s.stop(); } catch { /* already stopped */ }
    });
    this.sources = [];
    this.queue = [];
    this.nextTime = 0;
  }

  async playBase64Pcm(base64) {
    await this.init();
    if (this.ctx.state === "suspended") await this.ctx.resume();

    const floats = this._decodePcm16Base64(base64);
    const resampled = this.resample(floats, this.sourceSampleRate, this.ctx.sampleRate);

    if (this.useWorklet && this.node) {
      this.playing = true;
      this.node.port.postMessage({ type: "chunk", samples: resampled }, [resampled.buffer]);
      return;
    }

    const buffer = this.ctx.createBuffer(1, resampled.length, this.ctx.sampleRate);
    buffer.copyToChannel(resampled, 0);
    this.queue.push(buffer);
    this._scheduleAhead();
  }

  _scheduleAhead() {
    if (!this.ctx || !this.queue.length) return;
    const now = this.ctx.currentTime;
    const horizon = now + 0.25;
    if (!this.playing && this.nextTime < now) {
      this.nextTime = now + 0.03;
    }
    while (this.queue.length && this.nextTime < horizon) {
      const buffer = this.queue.shift();
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(this.gain);
      this.sources.push(source);
      if (this.nextTime < now) this.nextTime = now + 0.03;
      source.start(this.nextTime);
      this.nextTime += buffer.duration;
      source.onended = () => {
        this.sources = this.sources.filter((s) => s !== source);
        if (this.queue.length) this._scheduleAhead();
        else if (!this.sources.length) this._finishDrain();
      };
      this.playing = true;
    }
  }

  _finishDrain() {
    this.playing = false;
    if (this.onDrainCallback) {
      const cb = this.onDrainCallback;
      this.onDrainCallback = null;
      cb();
    }
  }

  destroy() {
    this.interrupt();
    if (this.node) {
      this.node.disconnect();
      this.node = null;
    }
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
    }
    this.workletReady = false;
  }
}

function floatToPcm16Base64(float32) {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(int16.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

async function ensureMicrophone() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone not supported in this browser");
  }

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
  });

  captureContext = new (window.AudioContext || window.webkitAudioContext)();
  if (captureContext.state === "suspended") await captureContext.resume();

  const source = captureContext.createMediaStreamSource(mediaStream);
  processor = captureContext.createScriptProcessor(2048, 1, 1);
  silentGain = captureContext.createGain();
  silentGain.gain.value = 0;

  const ratio = captureContext.sampleRate / INPUT_RATE;

  processor.onaudioprocess = (event) => {
    if (!active || !sessionReady || !ws || ws.readyState !== WebSocket.OPEN) return;
    // Avoid echo false-interrupts while agent audio is playing
    if (agentSpeaking) return;
    const input = event.inputBuffer.getChannelData(0);
    const outLen = Math.floor(input.length / ratio);
    if (outLen <= 0) return;
    const resampled = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) resampled[i] = input[Math.floor(i * ratio)];
    ws.send(JSON.stringify({ type: "audio", data: floatToPcm16Base64(resampled) }));
  };

  source.connect(processor);
  processor.connect(silentGain);
  silentGain.connect(captureContext.destination);
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/voice`;
}

async function startSession() {
  if (active) return;
  hadError = false;
  sessionReady = false;
  active = true;
  latencyT0 = performance.now();
  latencySessionId = null;
  latencyClientEvents = [];
  redirectToLatency = false;
  successPanel?.classList.add("hidden");
  latencyLink?.classList.add("hidden");
  if (transcriptEl) transcriptEl.innerHTML = "";

  latPush(
    "client_session_start",
    "client",
    "User clicked Start Call",
    "Session initiated",
    0,
    { nodes: ["user", "voicejs"] },
  );

  setUiState("connecting");
  setStatus("Requesting microphone…", "gold");

  try {
    latencyMicStart = performance.now();
    await ensureMicrophone();
    latPush(
      "client_mic_permission",
      "client",
      "navigator.mediaDevices.getUserMedia()",
      "Microphone stream acquired",
      performance.now() - latencyMicStart,
      { nodes: ["user", "voicejs"], breakdown: { echo_cancellation: true, noise_suppression: true } },
    );

    setStatus("Connecting to agent…", "gold");

    player = new PcmPlayer(OUTPUT_RATE);
    latencyWsStart = performance.now();
    ws = new WebSocket(wsUrl());

    ws.onmessage = (event) => handleServerMessage(JSON.parse(event.data));

    ws.onerror = () => {
      hadError = true;
      setUiState("error");
      setStatus("Connection error — check server logs", "error");
    };

    ws.onclose = () => {
      if (active && !hadError && !sessionReady) {
        hadError = true;
        setUiState("error");
        setStatus("Connection closed. Check GEMINI_API_KEY in .env.", "error");
      }
      if (active) stopSession({ keepError: hadError });
    };

    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Connection timeout")), 15000);
      ws.addEventListener("open", () => {
        clearTimeout(timeout);
        latPush(
          "client_ws_open",
          "network",
          `WebSocket ${wsUrl()}`,
          "WebSocket OPEN",
          performance.now() - latencyWsStart,
          { nodes: ["voicejs", "ws"] },
        );
        resolve();
      }, { once: true });
      ws.addEventListener("error", () => { clearTimeout(timeout); reject(new Error("WebSocket failed")); }, { once: true });
    });

    setStatus("Waiting for agent…", "gold");
    await waitForReady();
  } catch (err) {
    console.error(err);
    hadError = true;
    setUiState("error");
    if (err.name === "NotAllowedError") {
      setStatus("Microphone permission denied — allow access and try again", "error");
    } else if (err.name === "NotFoundError") {
      setStatus("No microphone found — connect a mic and try again", "error");
    } else {
      setStatus(`Error: ${err.message}`, "error");
    }
    stopSession({ keepError: true });
  }
}

function finishAgentTurn() {
  agentSpeaking = false;
  turnCompletePending = false;
  setUiState("listening");
  setStatus("Listening — speak in English (IST)", "green");
}

function handleServerMessage(msg) {
  switch (msg.type) {
    case "ready":
      sessionReady = true;
      agentSpeaking = false;
      turnCompletePending = false;
      latencySessionId = msg.session_id || null;
      updateLatencyLink();
      resolveReady();
      latPush(
        "client_ready_received",
        "network",
        "Server → { type: ready }",
        `Session ${latencySessionId || "ready"} — mic streaming enabled`,
        null,
        { nodes: ["ws", "voicejs", "user"] },
      );
      setUiState("listening");
      setStatus("Listening — speak in English (IST)", "green");
      break;
    case "audio":
      agentSpeaking = true;
      turnCompletePending = false;
      setUiState("speaking");
      setStatus("Speaking…", "gold");
      player?.playBase64Pcm(msg.data);
      break;
    case "transcript":
      appendTranscript(msg.role, msg.text, Boolean(msg.finished));
      if (msg.role === "user" && !agentSpeaking && !player?.isPlaying()) {
        setUiState("listening");
        setStatus("Listening — speak in English (IST)", "green");
      }
      break;
    case "interrupted":
      agentSpeaking = false;
      turnCompletePending = false;
      player?.interrupt();
      setUiState("listening");
      setStatus("Listening — interrupted", "green");
      break;
    case "turn_complete":
      turnCompletePending = true;
      if (player?.isPlaying()) {
        player.whenIdle(finishAgentTurn);
      } else {
        finishAgentTurn();
      }
      break;
    case "session_summary":
      if (msg.session_id) {
        latencySessionId = msg.session_id;
        updateLatencyLink();
        redirectToLatency = true;
      }
      break;
    case "error":
      hadError = true;
      if (readyWaiter) {
        readyWaiter.reject(new Error(msg.message || "Voice session error"));
        readyWaiter = null;
      }
      setUiState("error");
      setStatus(msg.message, "error");
      break;
  }
}

function stopSession({ keepError = false, autoLatency = true } = {}) {
  const sid = latencySessionId;
  const shouldRedirect = autoLatency && redirectToLatency && sid && !hadError;

  flushLatencyReport();
  active = false;
  sessionReady = false;

  const finishClose = () => {
    processor?.disconnect();
    processor = null;
    silentGain?.disconnect();
    silentGain = null;
    captureContext?.close();
    captureContext = null;
    mediaStream?.getTracks().forEach((t) => t.stop());
    mediaStream = null;
    player?.destroy();
    player = null;

    if (!keepError) {
      setUiState("idle");
      setStatus("Tap the microphone to start", "muted");
    }

    if (shouldRedirect) {
      setTimeout(() => {
        window.location.href = `/latency?session=${sid}`;
      }, 1200);
    }
  };

  if (ws) {
    ws.onclose = null;
    const sock = ws;
    ws = null;
    setTimeout(() => {
      sock.close();
      finishClose();
    }, 200);
  } else {
    finishClose();
  }
}

async function checkVoiceConfig() {
  try {
    const res = await fetch("/api/voice/status");
    const data = await res.json();
    if (!data.configured) {
      setUiState("error");
      setStatus("Voice not configured — set GEMINI_API_KEY in .env", "error");
    }
  } catch {
    /* ignore */
  }
}

setUiState("idle");
checkVoiceConfig();
