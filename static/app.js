// Kachra Report Card front end. Plain JS, no build step.
// The API defaults to the same origin; add ?api=https://your-api.onrender.com to point elsewhere.
"use strict";

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const GRADE_COLOR = { A: "var(--pass)", B: "var(--warn)", C: "var(--pen)" };
const GRADE_WORD = { A: "Good job!", B: "Needs attention", C: "Oops!" };
const STREAM_COLOR = { wet: "var(--wet)", dry: "var(--dry)", sanitary: "var(--san)", special_care: "var(--spc)" };
const BIN_SVG = (s, cls = "") => `<svg class="${cls}" style="color:${STREAM_COLOR[s]}" aria-hidden="true"><use href="#bin"/></svg>`;
const PLAY_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5Z"/></svg>';
// A Bhawan's letter grade from its 0-100 score.
const letter = (score) => (score >= 80 ? "A" : score >= 60 ? "B" : "C");
let days = 7;
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

async function api(path, opts = {}, timeoutMs = 60000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let r;
  try {
    r = await fetch(API + path, { ...opts, signal: ctrl.signal });
  } catch (e) {
    throw new Error(e.name === "AbortError" ? "The server took too long. Try again." : "No connection to the server.");
  } finally {
    clearTimeout(timer);
  }
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
  let rows, sum, recent, today;
  try {
    [rows, sum, recent, today] = await Promise.all([
      api(`/api/leaderboard?days=${days}`),
      api(`/api/summary?days=${days}`),
      api("/api/reports?limit=8"),
      api("/api/summary?days=1"),
    ]);
  } catch (e) {
    $("#board").innerHTML = `<li class="row empty-row">${esc(e.message)}</li>`;
    return;
  }
  renderHero(today, sum, rows);
  renderBoard(rows);
  drawTrend(sum.daily);
  drawStreams(sum.by_stream);
  loadIssues();
  renderFeed(recent);
}

$$(".range button").forEach((b) => b.addEventListener("click", () => {
  days = Number(b.dataset.days);
  $$(".range button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  loadBoard();
}));

// The hero: today's campus grade, a teacher's remark and three marks.
function renderHero(today, week, rows) {
  const lastDay = week.daily[week.daily.length - 1];
  const score = today.reports ? today.daily.at(-1)?.score ?? 0 : lastDay?.score;
  const grade = score == null ? "–" : letter(score);
  const stamp = $("#campus-grade");
  stamp.textContent = grade;
  stamp.className = `stamp-xl g-${grade}`;
  void stamp.offsetWidth;            // restart the landing animation
  stamp.classList.add("landed");
  $("#campus-score").textContent = score ?? "–";
  $("#hero-title").textContent = today.reports ? "Campus grade, today" : "Campus grade, latest day";

  const items = {};
  rows.forEach((r) => r.top_wrong_items.forEach((it, i) => { items[it] = (items[it] || 0) + 3 - i; }));
  const worst = Object.entries(items).sort((x, y) => y[1] - x[1])[0]?.[0];
  const best = rows[0]?.bhawan;
  $("#remark").textContent =
    score == null ? "No bins checked yet. The first photo starts the report card." :
    grade === "A" ? `Excellent work, Roorkee.${best ? ` ${best} leads the class.` : ""}` :
    grade === "B" ? `Good effort.${worst ? ` Keep ${worst} out of the wrong bins.` : ""}` :
    `Needs work.${worst ? ` Too much ${worst} in the wrong bins.` : ""}`;

  const fix = week.issues.avg_hours_to_fix;
  $("#marks").innerHTML = `
    <div class="mark"><dd>${week.segregation_rate}%</dd><dt>bins clean</dt><small>${week.reports.toLocaleString("en-IN")} checked in ${week.days === 1 ? "a day" : week.days + " days"}</small></div>
    <div class="mark"><dd>~${week.compost_kg_estimate.toLocaleString("en-IN")} kg</dd><dt>ready for compost</dt><small>estimate: ${week.wet_bins_compost_ready} clean wet bins × ${week.kg_per_wet_bin} kg</small></div>
    <div class="mark"><dd>${week.issues.open}</dd><dt>open complaints</dt><small>${fix != null ? `fixed in ${fix} h on average` : "none fixed yet"}</small></div>`;
}

function renderBoard(rows) {
  const board = $("#board");
  board.classList.remove("landed");
  board.innerHTML = rows.length ? rows.map(boardRow).join("")
    : `<li class="row empty-row">No bins checked in this period. Send the first one from "Check a bin".</li>`;
  void board.offsetWidth;
  board.classList.add("landed");
}

function boardRow(r, i) {
  const n = r.reports || 1;
  const pct = (k) => (100 * r.grades[k]) / n;
  const g = letter(r.score);
  const trend = r.trend > 0 ? `<span class="trend-up">▲ ${r.trend} today</span>`
    : r.trend < 0 ? `<span class="trend-down">▼ ${Math.abs(r.trend)} today</span>` : "";
  const wrong = r.top_wrong_items.length ? "Found: " + esc(r.top_wrong_items.join(", ")) : "Nothing in the wrong bin";
  return `<li class="row" style="--i:${i}">
    ${i < 3 ? '<svg class="star" aria-hidden="true"><use href="#star"/></svg>' : ""}
    <div class="rank">${r.rank}</div>
    <div class="name">${esc(r.bhawan)}<small>${r.reports} bins checked</small></div>
    <div class="mid">
      <div class="bar" role="img" aria-label="${r.grades.A} clean, ${r.grades.B} slightly mixed, ${r.grades.C} mixed">
        <i class="a" style="width:${pct("A")}%"></i><i class="b" style="width:${pct("B")}%"></i><i class="c" style="width:${pct("C")}%"></i>
      </div>
      <div class="wrong">${wrong}</div>
    </div>
    <div class="score">${r.score}<small>/100</small>${trend}</div>
    <div class="stamp g-${g}" aria-label="Grade ${g}">${g}</div>
    <button class="play" data-bhawan="${esc(r.bhawan)}" aria-label="Play ${esc(r.bhawan)}'s voice report">${PLAY_SVG}</button>
  </li>`;
}

function drawStreams(byStream) {
  $("#streams").innerHTML = Object.entries(byStream).map(([s, v]) => `
    <li>
      ${BIN_SVG(s)}
      <div><div class="sname">${STREAM_NAME[s]} bins</div>
        <div class="sbar"><i style="width:${v.clean_rate ?? 0}%;background:${STREAM_COLOR[s]}"></i></div></div>
      <span class="sval">${v.clean_rate == null ? "–" : v.clean_rate + "%"}</span>
    </li>`).join("");
}

async function loadIssues() {
  const list = await api("/api/issues?status=open").catch(() => []);
  $("#issue-note").textContent = list.length ? `${list.length} pinned` : "";
  $("#issues").innerHTML = list.length ? list.map((i) => `
    <li>
      <b>${esc(i.bhawan)}</b>
      <div class="what">${ISSUE_NAME[i.kind] || esc(i.kind)}${i.note ? ` – ${esc(i.note)}` : ""}</div>
      <div class="meta">${timeAgo(i.created_at)}${i.reporter ? `, by ${esc(i.reporter)}` : ""}</div>
      <button class="fix" data-id="${i.id}">Mark fixed</button>
    </li>`).join("") : `<li class="empty">Nothing pinned. Every bin was emptied on time.</li>`;
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

function renderFeed(recent) {
  $("#recent").innerHTML = recent.length ? recent.map((r) => {
    const text = r.status === "graded" ? r.tag : r.status === "failed" ? `Not graded: ${r.error || ""}` : "Grading…";
    return `<li>
      <span class="pill" style="--c:${GRADE_COLOR[r.grade] || "var(--ink-soft)"}">${r.grade || "…"}</span>
      <div><div>${esc(text)}</div>
      <div class="meta">${esc(r.bhawan)}, ${STREAM_NAME[r.bin_stream] || r.bin_stream} bin, ${timeAgo(r.created_at)}</div></div>
    </li>`;
  }).join("") : "<li>No checks yet.</li>";
}

function drawTrend(daily) {
  const svg = $("#trend");
  if (!daily.length) { svg.innerHTML = `<text x="24" y="100">No data yet</text>`; return; }
  const W = 640, H = 200, L = 38, R = 30, T = 22, B = 30;
  const x = (i) => L + (daily.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (daily.length - 1));
  const y = (v) => T + ((100 - v) * (H - T - B)) / 100;
  const grid = [0, 60, 80, 100].map((v) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="6" y="${y(v) + 4}">${v}</text>`).join("");
  const pts = daily.map((d, i) => `${x(i)},${y(d.score)}`);
  const area = `<path class="area" d="M${x(0)},${y(0)} L${pts.join(" L")} L${x(daily.length - 1)},${y(0)} Z"/>`;
  const dots = daily.map((d, i) => `<circle class="dot" cx="${x(i)}" cy="${y(d.score)}" r="4.5"><title>${d.date}: ${d.score} (${d.reports} bins)</title></circle>`).join("");
  const fmt = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  const step = Math.ceil(daily.length / 8);
  const labels = daily.map((d, i) => (i % step === 0 || i === daily.length - 1)
    ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${fmt(d.date)}</text>` : "").join("");
  const last = daily[daily.length - 1];
  const lastLabel = `<text class="last" x="${x(daily.length - 1) - 6}" y="${y(last.score) - 12}" text-anchor="end">${last.score}</text>`;
  svg.innerHTML = grid + area + `<polyline class="line" points="${pts.join(" ")}"/>` + dots + labels + lastLabel;
}

// "Listen" plays the warden's ElevenLabs voice note, or the browser reads the text if TTS is off.
let audioEl = null;
$("#board").addEventListener("click", async (e) => {
  const btn = e.target.closest(".play");
  if (!btn) return;
  btn.setAttribute("aria-busy", "true");
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
    btn.removeAttribute("aria-busy");
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
      <svg aria-hidden="true"><use href="#bin"/></svg>
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
  submit.textContent = "Marking…";
  try {
    showResult(await api("/api/reports?wait=1", { method: "POST", body: fd }));
  } catch (err) {
    setError(err.message);
  } finally {
    submit.disabled = false;
    submit.textContent = "Check this bin";
  }
};

function showResult(r) {
  const res = $("#result");
  if (r.status !== "graded") {
    res.innerHTML = `<div class="tag g-C"><div class="tag-head"><div class="tag-word">Try again</div></div>
      <p>${esc(r.error || "The bin could not be graded.")}</p></div>`;
    return;
  }
  const message = r.tag.replace(/^(Good job!|Oops!|Needs attention:)\s*/, "");
  const items = r.found_items?.length ? `<ul class="items">${r.found_items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  res.innerHTML = `<div class="tag g-${r.grade}">
      <div class="tag-head">
        <div class="stamp-xl g-${r.grade} landed">${r.grade}</div>
        <div class="tag-word">${GRADE_WORD[r.grade]}</div>
      </div>
      <p>${esc(message)}</p>
      ${items}
      <p class="meta">${esc(r.bhawan)}, ${STREAM_NAME[r.bin_stream].toLowerCase()} bin. About ${r.contamination}% of what's inside belongs in another bin.</p>
    </div>
    <button class="again" type="button">Check the next bin</button>`;
  res.querySelector(".again").onclick = resetForm;
  if (window.matchMedia("(max-width: 860px)").matches) res.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetForm() {
  $("#report-form").reset();
  $("#photo-preview").hidden = true;
  $("#photo-hint").hidden = false;
  pickStream(null);
  $("#bhawan").value = store.get() || "";
  $("#result").innerHTML = `<div class="result-empty"><div class="stamp-ghost">A</div><p>The grade appears here, stamped, in about five seconds.</p></div>`;
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
