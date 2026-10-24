// Kachra Report Card front end. Plain JS, no build step.
// The API defaults to the same origin; add ?api=https://your-api.onrender.com to point elsewhere.
"use strict";

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const GRADE_COLOR = { A: "var(--grade-a)", B: "var(--grade-b)", C: "var(--grade-c)" };
const GRADE_WORD = { A: "Good job!", B: "Needs attention", C: "Oops!" };
const STREAM_NAME = { wet: "Wet", dry: "Dry", sanitary: "Sanitary", special_care: "Special care" };
const STREAM_HINT = {
  wet: "food, peels, tea leaves",
  dry: "plastic, paper, bottles",
  sanitary: "diapers, pads",
  special_care: "medicines, bulbs, batteries",
};
const ISSUE_NAME = { overflow: "Bin is full", missed_pickup: "Pickup missed", broken_bin: "Bin is broken", other: "Other" };
// Workers may speak Hindi, so voice autofill also understands common Hindi words.
const SPOKEN_STREAM = {
  wet: "wet", geela: "wet", gila: "wet", food: "wet",
  dry: "dry", sookha: "dry", sukha: "dry",
  sanitary: "sanitary",
  special: "special_care", hazardous: "special_care", dawai: "special_care",
};

const store = {
  get() { try { return localStorage.getItem("kachra.bhawan"); } catch { return null; } },
  set(v) { try { localStorage.setItem("kachra.bhawan", v); } catch { /* storage blocked */ } },
};

let META = null;
let pickedStream = null;

/* ---------- helpers ---------- */

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Server error ${r.status}`);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function timeAgo(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

function setError(msg) { $("#form-error").textContent = msg || ""; }

/* ---------- tabs ---------- */

function showTab(which) {
  for (const t of ["board", "report"]) {
    $(`#tab-${t}`).setAttribute("aria-selected", String(t === which));
    $(`#view-${t}`).hidden = t !== which;
  }
  if (which === "board") loadBoard();
  history.replaceState(null, "", (location.search || "") + (which === "report" ? "#report" : ""));
}
$("#tab-board").onclick = () => showTab("board");
$("#tab-report").onclick = () => showTab("report");

/* ---------- leaderboard ---------- */

async function loadBoard() {
  const days = $("#days").value;
  let rows, sum, recent;
  try {
    [rows, sum, recent] = await Promise.all([
      api(`/api/leaderboard?days=${days}`),
      api(`/api/summary?days=${days}`),
      api("/api/reports?limit=8"),
    ]);
  } catch (e) {
    $("#board").innerHTML = `<li class="row">${esc(e.message)}</li>`;
    return;
  }

  const fix = sum.issues.avg_hours_to_fix;
  $("#summary").innerHTML = `
    <div class="stat"><b>${sum.segregation_rate}%</b><span>of ${sum.reports.toLocaleString("en-IN")} bins checked were clean</span></div>
    <div class="stat"><b>~${sum.compost_kg_estimate.toLocaleString("en-IN")} kg</b><span>wet waste ready for compost (estimate: ${sum.wet_bins_compost_ready} clean wet bins × ${sum.kg_per_wet_bin} kg)</span></div>
    <div class="stat"><b>${sum.issues.open}</b><span>open complaints${fix != null ? `, fixed in ${fix} h on average` : ""}</span></div>`;

  $("#board").innerHTML = rows.length ? rows.map(boardRow).join("")
    : `<li class="row empty-row">No reports yet. Send the first one from "Report a bin".</li>`;

  drawTrend(sum.daily);
  drawStreams(sum.by_stream);
  loadIssues();

  $("#recent").innerHTML = recent.map((r) => {
    const text = r.status === "graded" ? r.tag : r.status === "failed" ? `Not graded: ${r.error || ""}` : "Grading…";
    return `<li>
      <span class="pill" style="background:${GRADE_COLOR[r.grade] || "var(--muted)"}">${r.grade || "…"}</span>
      <div><div>${esc(text)}</div>
      <div class="meta">${esc(r.bhawan)}, ${STREAM_NAME[r.bin_stream] || r.bin_stream} bin, ${timeAgo(r.created_at)}</div></div>
    </li>`;
  }).join("");
}
$("#days").onchange = loadBoard;

function boardRow(r) {
  const n = r.reports || 1;
  const pct = (k) => (100 * r.grades[k]) / n;
  const trend = r.trend > 0 ? `<div class="trend-up">+${r.trend} vs week</div>`
    : r.trend < 0 ? `<div class="trend-down">${r.trend} vs week</div>` : "";
  const wrong = r.top_wrong_items.length ? "Wrong items: " + esc(r.top_wrong_items.join(", ")) : "No wrong items found";
  return `<li class="row">
    <div class="rank">${r.rank}</div>
    <div class="name">${esc(r.bhawan)}<small>${r.reports} bins</small></div>
    <div class="mid">
      <div class="bar" role="img" aria-label="${r.grades.A} clean, ${r.grades.B} slightly mixed, ${r.grades.C} mixed">
        <i class="a" style="width:${pct("A")}%"></i><i class="b" style="width:${pct("B")}%"></i><i class="c" style="width:${pct("C")}%"></i>
      </div>
      <div class="wrong">${wrong}</div>
    </div>
    <div class="score"><b>${r.score}</b>${trend}
      <button class="play" data-bhawan="${esc(r.bhawan)}" aria-label="Play ${esc(r.bhawan)}'s voice report">Listen</button>
    </div>
  </li>`;
}

// Share of each bin type graded A.
function drawStreams(byStream) {
  $("#streams").innerHTML = Object.entries(byStream).map(([s, v]) => `
    <li>
      <span class="sname"><i class="sw bin-${s}"></i>${STREAM_NAME[s]}</span>
      <span class="sbar"><i style="width:${v.clean_rate ?? 0}%"></i></span>
      <span class="sval">${v.clean_rate == null ? "–" : v.clean_rate + "%"}</span>
    </li>`).join("");
}

async function loadIssues() {
  const list = await api("/api/issues?status=open").catch(() => []);
  $("#issues").innerHTML = list.length ? list.map((i) => `
    <li>
      <div><b>${esc(i.bhawan)}</b>: ${ISSUE_NAME[i.kind] || esc(i.kind)}${i.note ? ` – "${esc(i.note)}"` : ""}
        <div class="meta">${timeAgo(i.created_at)}</div></div>
      <button class="fix" data-id="${i.id}">Mark fixed</button>
    </li>`).join("") : `<li class="empty">No open complaints.</li>`;
}
$("#issues").addEventListener("click", async (e) => {
  const b = e.target.closest(".fix");
  if (!b) return;
  b.disabled = true;
  try {
    await api(`/api/issues/${b.dataset.id}/resolve`, { method: "POST" });
    loadBoard();
  } catch (err) {
    b.disabled = false;
    alert(err.message);
  }
});

function drawTrend(daily) {
  const svg = $("#trend");
  if (!daily.length) { svg.innerHTML = `<text x="20" y="90">No data yet</text>`; return; }
  const W = 640, H = 180, L = 36, R = 16, T = 16, B = 28;
  const x = (i) => L + (daily.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (daily.length - 1));
  const y = (v) => T + ((100 - v) * (H - T - B)) / 100;
  const grid = [0, 50, 100].map((v) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="4" y="${y(v) + 4}">${v}</text>`).join("");
  const pts = daily.map((d, i) => `${x(i)},${y(d.score)}`).join(" ");
  const dots = daily.map((d, i) => `<circle class="dot" cx="${x(i)}" cy="${y(d.score)}" r="4"><title>${d.date}: ${d.score} (${d.reports} bins)</title></circle>`).join("");
  const fmt = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  const labels = daily.map((d, i) => `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${fmt(d.date)}</text>`).join("");
  svg.innerHTML = grid + `<polyline class="line" points="${pts}"/>` + dots + labels;
}

// "Listen" plays the warden's ElevenLabs voice note, or the browser reads the text if TTS is off.
let audioEl = null;
$("#board").addEventListener("click", async (e) => {
  const btn = e.target.closest(".play");
  if (!btn) return;
  btn.textContent = "Loading…";
  btn.disabled = true;
  try {
    const b = await api(`/api/briefing/${encodeURIComponent(btn.dataset.bhawan)}`);
    if (b.audio_url) {
      audioEl?.pause();
      audioEl = new Audio(API + b.audio_url);
      await audioEl.play();
    } else if ("speechSynthesis" in window) {
      speechSynthesis.cancel();
      speechSynthesis.speak(Object.assign(new SpeechSynthesisUtterance(b.text), { lang: "en-IN" }));
    } else {
      alert(b.text);
    }
  } catch (err) {
    alert(err.message);
  } finally {
    btn.textContent = "Listen";
    btn.disabled = false;
  }
});

/* ---------- report form ---------- */

function buildForm() {
  $("#bhawan").innerHTML = `<option value="">Choose your Bhawan</option>` +
    META.bhawans.map((b) => `<option>${esc(b)}</option>`).join("");
  const saved = store.get();
  if (saved && META.bhawans.includes(saved)) $("#bhawan").value = saved;

  $("#bins").innerHTML = META.streams.map((s) => `
    <button type="button" class="bin bin-${s}" data-stream="${s}" aria-pressed="false">
      <b>${STREAM_NAME[s]}</b><small>${STREAM_HINT[s]}</small>
    </button>`).join("");
  $("#bins").onclick = (e) => {
    const b = e.target.closest(".bin");
    if (b) pickStream(b.dataset.stream);
  };

  if (META.agent_id) {
    $("#agent").hidden = false;
    $("#agent-slot").innerHTML = `<elevenlabs-convai agent-id="${esc(META.agent_id)}"></elevenlabs-convai>`;
    const s = document.createElement("script");
    s.src = "https://unpkg.com/@elevenlabs/convai-widget-embed";
    s.async = true;
    document.body.appendChild(s);
  }
}

function pickStream(stream) {
  pickedStream = stream;
  $("#bins").classList.toggle("picked", Boolean(stream));
  $$(".bin").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.stream === stream)));
}

$("#photo").onchange = () => {
  const f = $("#photo").files[0];
  if (!f) return;
  const img = $("#photo-preview");
  img.src = URL.createObjectURL(f);
  img.hidden = false;
  $("#photo-hint").hidden = true;
};

// Voice note -> ElevenLabs Scribe (server) -> text box. Falls back to the browser's recogniser.
let recorder = null;
$("#mic").onclick = async () => {
  if (recorder?.state === "recording") { recorder.stop(); return; }
  if (!META.stt) { browserDictation(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => onRecordingDone(stream, chunks);
    recorder.start();
    $("#mic").setAttribute("aria-pressed", "true");
    $("#mic-label").textContent = "Tap to stop";
  } catch {
    setError("Microphone permission was not given. Type the note instead.");
  }
};

async function onRecordingDone(stream, chunks) {
  stream.getTracks().forEach((t) => t.stop());
  $("#mic").setAttribute("aria-pressed", "false");
  $("#mic-label").textContent = "Transcribing…";
  const fd = new FormData();
  fd.append("audio", new Blob(chunks, { type: recorder.mimeType }), "note.webm");
  try {
    const { text } = await api("/api/transcribe", { method: "POST", body: fd });
    $("#note").value = text;
    autofillFromSpeech(text);
  } catch (err) {
    setError(err.message);
  }
  $("#mic-label").textContent = "Speak";
}

function browserDictation() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { setError("Voice input isn't available in this browser. Type the note instead."); return; }
  const rec = new SR();
  rec.lang = "en-IN";
  $("#mic").setAttribute("aria-pressed", "true");
  rec.onresult = (e) => { const t = e.results[0][0].transcript; $("#note").value = t; autofillFromSpeech(t); };
  rec.onend = () => $("#mic").setAttribute("aria-pressed", "false");
  rec.start();
}

// "Govind Bhawan, wet bin, plastic bag on top" fills the Bhawan and bin for the worker.
function autofillFromSpeech(text) {
  const t = text.toLowerCase();
  const b = META.bhawans.find((x) => t.includes(x.toLowerCase()));
  if (b) $("#bhawan").value = b;
  const hit = Object.keys(SPOKEN_STREAM).find((k) => new RegExp(`\\b${k}`).test(t));
  if (hit) pickStream(SPOKEN_STREAM[hit]);
}

$("#report-form").onsubmit = async (e) => {
  e.preventDefault();
  setError("");
  const bhawan = $("#bhawan").value;
  if (!bhawan) return setError("Choose your Bhawan.");
  if (!pickedStream) return setError("Choose which bin this is.");
  if (!$("#photo").files[0] && !$("#note").value.trim()) return setError("Take a photo of the bin or add a note.");
  store.set(bhawan);

  const fd = new FormData($("#report-form"));
  fd.set("bin_stream", pickedStream);
  const submit = $("#submit");
  submit.disabled = true;
  submit.textContent = "Checking the bin…";
  try {
    showResult(await api("/api/reports?wait=1", { method: "POST", body: fd }));
  } catch (err) {
    setError(err.message);
  } finally {
    submit.disabled = false;
    submit.textContent = "Send report";
  }
};

function showResult(r) {
  const res = $("#result");
  res.hidden = false;
  if (r.status !== "graded") {
    res.innerHTML = `<div class="tag tag-C"><span class="stamp">Try again</span><p>${esc(r.error || "The bin could not be graded.")}</p></div>`;
    return;
  }
  const message = r.tag.replace(/^(Good job!|Oops!|Needs attention:)\s*/, "");
  res.innerHTML = `<div class="tag tag-${r.grade}">
      <span class="stamp">${GRADE_WORD[r.grade]}</span>
      <p>${esc(message)}</p>
      <p class="meta">${esc(r.bhawan)}, ${STREAM_NAME[r.bin_stream]} bin: grade ${r.grade}, about ${r.contamination}% wrong items</p>
    </div>
    <button class="again" type="button">Report the next bin</button>`;
  res.querySelector(".again").onclick = resetForm;
  res.scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetForm() {
  $("#report-form").reset();
  $("#photo-preview").hidden = true;
  $("#photo-hint").hidden = false;
  pickStream(null);
  $("#bhawan").value = store.get() || "";
  $("#result").hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("#quick").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const bhawan = $("#bhawan").value;
  if (!bhawan) { $("#quick-msg").textContent = "Choose your Bhawan above first."; return; }
  b.disabled = true;
  try {
    const r = await api("/api/issues", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ bhawan, kind: b.dataset.kind, reporter: $("#reporter").value || null }),
    });
    $("#quick-msg").textContent = `Complaint #${r.id} logged for ${r.bhawan}: ${b.textContent}.`;
  } catch (err) {
    $("#quick-msg").textContent = err.message;
  } finally {
    b.disabled = false;
  }
});

// A QR sticker on each bin opens /?b=Govind&s=wet, so the worker only takes the photo.
function prefillFromLink() {
  const q = new URLSearchParams(location.search);
  const b = q.get("b"), s = q.get("s");
  if (b && META.bhawans.includes(b)) $("#bhawan").value = b;
  if (s && META.streams.includes(s)) pickStream(s);
  return Boolean(b || s);
}

/* ---------- start ---------- */

(async function init() {
  try {
    META = await api("/api/meta");
  } catch (e) {
    $("#board").innerHTML = `<li class="row">Could not reach the server: ${esc(e.message)}</li>`;
    return;
  }
  buildForm();
  const fromQr = prefillFromLink();
  showTab(location.hash === "#report" || fromQr ? "report" : "board");
})();
