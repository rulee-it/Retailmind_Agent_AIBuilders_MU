// =============================================================
// RetailMind v2 — chat client
// Vanilla ES module. Talks to FastAPI on the same origin.
// =============================================================

const API = window.location.origin;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---- session id (persisted in localStorage) ----
const SESSION_KEY = "retailmind_session_id";
function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
let sessionId = localStorage.getItem(SESSION_KEY);
if (!sessionId) {
  sessionId = uuid();
  localStorage.setItem(SESSION_KEY, sessionId);
}

// ---- markdown ----
const md = (text) =>
  marked.parse(text || "", { gfm: true, breaks: true, mangle: false, headerIds: false });

// =============================================================
// Snapshot tiles
// =============================================================
async function loadSummary() {
  try {
    const r = await fetch(`${API}/summary`);
    const j = await r.json();
    const tiles = $$("#snapshot-tiles .tile");
    const fmt = (v, suf = "") => `${v}${suf}`;
    const values = [
      fmt(j.total_skus),
      fmt(j.critical_stock_count),
      fmt(j.avg_margin_percent, "%"),
      fmt(j.avg_rating, " ★"),
    ];
    tiles.forEach((tile, i) => {
      tile.classList.remove("loading");
      tile.querySelector(".tile-val").textContent = values[i];
    });
  } catch (e) {
    console.warn("summary fetch failed", e);
  }
}

// =============================================================
// Categories dropdown
// =============================================================
async function loadCategories() {
  try {
    const r = await fetch(`${API}/categories`);
    const j = await r.json();
    const sel = $("#cat-filter");
    sel.innerHTML = "";
    (j.categories || []).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.warn("categories fetch failed", e);
  }
}

// =============================================================
// Chat panel state
// =============================================================
const panel = $("#chat-panel");
const scrim = $("#chat-scrim");
const stream = $("#chat-stream");
const form = $("#chat-form");
const input = $("#chat-input");
const sendBtn = form.querySelector(".send-btn");

let briefingLoaded = false;
let lastTrace = null;

function openPanel(prefill) {
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  scrim.classList.add("open");
  if (prefill) {
    input.value = prefill;
    autoresize();
  }
  if (!briefingLoaded) {
    loadBriefing();
    briefingLoaded = true;
  }
  setTimeout(() => input.focus(), 320);
}
function closePanel() {
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
  scrim.classList.remove("open");
}

$("#chat-fab").addEventListener("click", () => openPanel());
$("#open-chat-hero").addEventListener("click", () => openPanel());
$("#open-chat-top").addEventListener("click", (e) => { e.preventDefault(); openPanel(); });
$("#close-btn").addEventListener("click", closePanel);
scrim.addEventListener("click", closePanel);
$("#scroll-how").addEventListener("click", () => $("#how").scrollIntoView({ behavior: "smooth" }));

$$("#sample-chips .chip").forEach((c) =>
  c.addEventListener("click", () => openPanel(c.dataset.q))
);

// =============================================================
// Daily briefing
// =============================================================
async function loadBriefing() {
  const card = document.createElement("div");
  card.className = "briefing-card";
  card.innerHTML = `<div class="md"><p style="color:var(--ink-soft); font-family:var(--mono); font-size:12px;">Orchestrating four specialists…</p></div>`;
  stream.prepend(card);
  try {
    const r = await fetch(`${API}/briefing?session_id=${encodeURIComponent(sessionId)}`);
    const j = await r.json();
    card.innerHTML = `<div class="md">${md(j.briefing || "_No briefing available._")}</div>`;
  } catch (e) {
    card.innerHTML = `<div class="md"><p style="color:var(--burgundy);">Failed to load briefing. Is the OpenAI key set?</p></div>`;
  }
}

// =============================================================
// Messages
// =============================================================
function renderUser(text) {
  const row = document.createElement("div");
  row.className = "msg user";
  row.innerHTML = `<div class="bubble"><div class="md">${md(text)}</div></div>`;
  stream.appendChild(row);
  stream.scrollTop = stream.scrollHeight;
}

function renderTyping() {
  const row = document.createElement("div");
  row.className = "msg assistant";
  row.dataset.typing = "1";
  row.innerHTML = `<div class="bubble" style="padding:0;"><div class="typing"><span></span><span></span><span></span></div></div>`;
  stream.appendChild(row);
  stream.scrollTop = stream.scrollHeight;
  return row;
}

function renderAssistant(payload, replaceNode) {
  const route = payload.route || "GENERAL";
  const specialists = payload.specialists || [];
  const html = `
    <div class="bubble"><div class="md">${md(payload.response || "")}</div></div>
    <div class="route-row">
      <span class="r-chip route ${route}">${route}</span>
      ${specialists
        .map((s) => `<span class="r-chip spec">${s.replace("Agent", "")}</span>`)
        .join("")}
    </div>
    <span class="trace-toggle">▾ trace</span>
    <div class="trace-body" hidden></div>
  `;
  const node = replaceNode || document.createElement("div");
  node.className = "msg assistant";
  delete node.dataset.typing;
  node.innerHTML = html;
  if (!replaceNode) stream.appendChild(node);

  // wire trace toggle
  const toggle = node.querySelector(".trace-toggle");
  const body = node.querySelector(".trace-body");
  toggle.addEventListener("click", async () => {
    if (!body.hidden) {
      body.hidden = true;
      toggle.textContent = "▾ trace";
      return;
    }
    toggle.textContent = "▴ trace";
    body.hidden = false;
    try {
      const r = await fetch(`${API}/trace/${encodeURIComponent(sessionId)}`);
      const t = await r.json();
      body.textContent = formatTrace(t);
    } catch {
      body.textContent = "trace unavailable";
    }
  });
  stream.scrollTop = stream.scrollHeight;
  $("#route-last").textContent = `last route: ${route}`;
}

function formatTrace(t) {
  if (!t || !t.route) return "no trace";
  const timings = Object.entries(t.timings_ms || {})
    .map(([k, v]) => `  ${k.padEnd(18)} ${v} ms`)
    .join("\n");
  return [
    `route       ${t.route}`,
    `reason      ${t.reason}`,
    `specialists ${(t.specialists_called || []).join(", ") || "—"}`,
    "",
    "timings:",
    timings || "  (none)",
  ].join("\n");
}

// =============================================================
// Send
// =============================================================
async function send(text) {
  if (!text.trim()) return;
  renderUser(text);
  input.value = "";
  autoresize();
  sendBtn.disabled = true;

  const typingNode = renderTyping();
  const category = $("#cat-filter").value || null;
  try {
    const r = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
        category_filter: category,
      }),
    });
    if (!r.ok) {
      const errText = await r.text();
      renderAssistant(
        { response: `**Error:** ${errText}`, route: "GENERAL", specialists: [] },
        typingNode
      );
      return;
    }
    const j = await r.json();
    renderAssistant(j, typingNode);
  } catch (e) {
    renderAssistant(
      { response: `**Network error:** ${e.message}`, route: "GENERAL", specialists: [] },
      typingNode
    );
  } finally {
    sendBtn.disabled = false;
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

function autoresize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
}
input.addEventListener("input", autoresize);

// =============================================================
// Clear
// =============================================================
$("#clear-btn").addEventListener("click", async () => {
  stream.innerHTML = "";
  briefingLoaded = false;
  try {
    const r = await fetch(`${API}/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const j = await r.json();
    const card = document.createElement("div");
    card.className = "briefing-card";
    card.innerHTML = `<div class="md">${md(j.briefing || "")}</div>`;
    stream.prepend(card);
    briefingLoaded = true;
  } catch (e) {
    loadBriefing();
  }
});

// =============================================================
// Boot
// =============================================================
loadSummary();
loadCategories();
