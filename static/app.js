// Kachra Report Card front end. Plain JS, no build step.
// API defaults to the same origin; add ?api=https://your-api.onrender.com to point elsewhere.

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const $ = (s) => document.querySelector(s);
const GRADE_COLOR = { A: "var(--grade-a)", B: "var(--grade-b)", C: "var(--grade-c)" };
const STREAM_NAME = { wet: "Geela", dry: "Sookha", sanitary: "Sanitary", special_care: "Special care" };
const STREAM_HINT = {
  wet: "khaana, chhilke, chai patti",
  dry: "plastic, kaagaz, bottle",
  sanitary: "diaper, pad",
  special_care: "dawai, bulb, battery",
};

const store = {
  get() { try { return localStorage.getItem("kachra.bhawan"); } catch { return null; } },
  set(v) { try { localStorage.setItem("kachra.bhawan", v); } catch {} },
};

let META = null;
let pickedStream = null;

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
  if (m < 1) return "abhi";
  if (m < 60) return `${m} min pehle`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} ghante pehle`;
  return `${Math.round(h / 24)} din pehle`;
}

/* ---------- Tabs ---------- */
function showTab(which) {
  for (const t of ["board", "report"]) {
    $(`#tab-${t}`).setAttribute("aria-selected", String(t === which));
    $(`#view-${t}`).hidden = t !== which;
  }
  if (which === "board") loadBoard();
  history.replaceState(null, "", which === "report" ? "#report" : "#");
}
$("#tab-board").onclick = () => showTab("board");
$("#tab-report").onclick = () => showTab("report");

/* ---------- Leaderboard ---------- */
async function loadBoard() {
  const days = $("#days").value;
  const [rows, sum, recent] = await Promise.all([
    api(`/api/leaderboard?days=${days}`),
    api(`/api/summary?days=${days}`),
    api(`/api/reports?limit=8`),
  ]).catch((e) => { $("#board").innerHTML = `<li>${esc(e.message)}</li>`; return [null]; });
  if (!rows) return;

  $("#summary").innerHTML = `
    <div class="stat"><b>${sum.segregation_rate}%</b><span>dabbe ekdum saaf mile</span></div>
    <div class="stat"><b>${sum.reports}</b><span>dabbe check hue</span></div>
    <div class="stat"><b>${sum.wet_bins_compost_ready}</b><span>geele dabbe compost ke layak</span></div>`;

  $("#board").innerHTML = rows.length ? rows.map((r) => {
    const n = r.reports || 1;
    const pct = (k) => (100 * r.grades[k]) / n;
    const trend = r.trend == null ? "" :
      r.trend > 0 ? `<div class="trend-up">+${r.trend} aaj</div>` :
      r.trend < 0 ? `<div class="trend-down">${r.trend} aaj</div>` : "";
    return `<li class="row">
      <div class="rank">${r.rank}</div>
      <div class="name">${esc(r.bhawan)}<small>${r.reports} dabbe</small></div>
      <div class="mid">
        <div class="bar" title="A ${r.grades.A} · B ${r.grades.B} · C ${r.grades.C}">
          <i class="a" style="width:${pct("A")}%"></i><i class="b" style="width:${pct("B")}%"></i><i class="c" style="width:${pct("C")}%"></i>
        </div>
        <div class="wrong">${r.top_wrong_items.length ? "Galat: " + esc(r.top_wrong_items.join(", ")) : "Koi galat cheez nahi mili"}</div>
      </div>
      <div class="score"><b>${r.score}</b>${trend}
        <button class="play" data-bhawan="${esc(r.bhawan)}" aria-label="${esc(r.bhawan)} ka voice report suno">Suno</button>
      </div>
    </li>`;
  }).join("") : `<li class="row"><div></div><div class="name">Abhi koi report nahi</div><div class="mid">Pehli report "Report karo" se bhejo.</div></li>`;

  drawTrend(sum.daily);

  $("#recent").innerHTML = recent.map((r) => `<li>
    <span class="pill" style="background:${GRADE_COLOR[r.grade] || "var(--muted)"}">${r.grade || "…"}</span>
    <div><div>${esc(r.tag_hi || (r.status === "failed" ? "Grade nahi ho paya: " + (r.error || "") : "Grade ho raha hai…"))}</div>
    <div class="meta">${esc(r.bhawan)}, ${STREAM_NAME[r.bin_stream] || r.bin_stream} dabba, ${timeAgo(r.created_at)}</div></div>
  </li>`).join("");
}
$("#days").onchange = loadBoard;

function drawTrend(daily) {
  const svg = $("#trend");
  if (!daily.length) { svg.innerHTML = `<text x="20" y="90">Data aane do</text>`; return; }
  const W = 640, H = 180, L = 36, R = 16, T = 16, B = 28;
  const x = (i) => L + (daily.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (daily.length - 1));
  const y = (v) => T + ((100 - v) * (H - T - B)) / 100;
  const grid = [0, 50, 100].map((v) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="4" y="${y(v) + 4}">${v}</text>`).join("");
  const pts = daily.map((d, i) => `${x(i)},${y(d.score)}`).join(" ");
  const dots = daily.map((d, i) => `<circle class="dot" cx="${x(i)}" cy="${y(d.score)}" r="4"><title>${d.date}: ${d.score} (${d.reports} dabbe)</title></circle>`).join("");
  const labels = daily.map((d, i) => `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${d.date.slice(8)}/${d.date.slice(5, 7)}</text>`).join("");
  svg.innerHTML = grid + `<polyline class="line" points="${pts}"/>` + dots + labels;
}

// "Suno" plays the warden's ElevenLabs voice note (or reads the text if TTS is off).
let audioEl = null;
$("#board").addEventListener("click", async (e) => {
  const btn = e.target.closest(".play");
  if (!btn) return;
  btn.textContent = "Ban raha hai…";
  try {
    const b = await api(`/api/briefing/${encodeURIComponent(btn.dataset.bhawan)}`);
    if (b.audio_url) {
      audioEl?.pause();
      audioEl = new Audio(API + b.audio_url);
      await audioEl.play();
    } else if ("speechSynthesis" in window) {
      const u = new SpeechSynthesisUtterance(b.text);
      u.lang = "hi-IN";
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    } else {
      alert(b.text);
    }
  } catch (err) {
    alert(err.message);
  } finally {
    btn.textContent = "Suno";
  }
});

/* ---------- Report form ---------- */
function buildForm() {
  $("#bhawan").innerHTML = `<option value="">Bhawan chuno</option>` +
    META.bhawans.map((b) => `<option>${esc(b)}</option>`).join("");
  const saved = store.get();
  if (saved) $("#bhawan").value = saved;

  $("#bins").innerHTML = META.streams.map((s) => `
    <button type="button" class="bin bin-${s}" data-stream="${s}" aria-pressed="false">
      <b>${STREAM_NAME[s]}</b><small>${STREAM_HINT[s]}</small>
    </button>`).join("");
  $("#bins").onclick = (e) => {
    const b = e.target.closest(".bin");
    if (!b) return;
    pickedStream = b.dataset.stream;
    $("#bins").classList.add("picked");
    document.querySelectorAll(".bin").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
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
  const mic = $("#mic");
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }
  if (!META.stt) return browserDictation();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      mic.setAttribute("aria-pressed", "false");
      $("#mic-label").textContent = "Samajh raha hai…";
      const fd = new FormData();
      fd.append("audio", new Blob(chunks, { type: recorder.mimeType }), "note.webm");
      try {
        const { text } = await api("/api/transcribe", { method: "POST", body: fd });
        $("#note").value = text;
        autofillFromSpeech(text);
      } catch (err) {
        $("#form-error").textContent = err.message;
      }
      $("#mic-label").textContent = "Bol ke batao";
    };
    recorder.start();
    mic.setAttribute("aria-pressed", "true");
    $("#mic-label").textContent = "Rokne ke liye dabao";
  } catch {
    $("#form-error").textContent = "Mic ki permission nahi mili. Note type kar do.";
  }
};

function browserDictation() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("#form-error").textContent = "Is browser mein voice nahi chalta. Note type kar do."; return; }
  const rec = new SR();
  rec.lang = "hi-IN";
  $("#mic").setAttribute("aria-pressed", "true");
  rec.onresult = (e) => { const t = e.results[0][0].transcript; $("#note").value = t; autofillFromSpeech(t); };
  rec.onend = () => $("#mic").setAttribute("aria-pressed", "false");
  rec.start();
}

// If the worker says "Govind Bhawan, geela dabba", pick those for them.
function autofillFromSpeech(text) {
  const t = text.toLowerCase();
  const b = META.bhawans.find((x) => t.includes(x.toLowerCase()));
  if (b) $("#bhawan").value = b;
  const map = { geela: "wet", gila: "wet", wet: "wet", sookha: "dry", sukha: "dry", dry: "dry", sanitary: "sanitary", special: "special_care", dawai: "special_care" };
  const hit = Object.keys(map).find((k) => t.includes(k));
  if (hit) document.querySelector(`.bin[data-stream="${map[hit]}"]`)?.click();
}

$("#report-form").onsubmit = async (e) => {
  e.preventDefault();
  $("#form-error").textContent = "";
  const bhawan = $("#bhawan").value;
  if (!bhawan) return ($("#form-error").textContent = "Bhawan chuno.");
  if (!pickedStream) return ($("#form-error").textContent = "Kaunsa dabba hai, chuno.");
  if (!$("#photo").files[0] && !$("#note").value.trim()) return ($("#form-error").textContent = "Photo lo ya kuch bolo.");
  store.set(bhawan);

  const fd = new FormData($("#report-form"));
  fd.set("bin_stream", pickedStream);
  $("#submit").disabled = true;
  $("#submit").textContent = "Check ho raha hai…";
  try {
    const r = await api("/api/reports?wait=1", { method: "POST", body: fd });
    showResult(r);
  } catch (err) {
    $("#form-error").textContent = err.message;
  } finally {
    $("#submit").disabled = false;
    $("#submit").textContent = "Report bhejo";
  }
};

function showResult(r) {
  const res = $("#result");
  res.hidden = false;
  if (r.status !== "graded") {
    res.innerHTML = `<div class="tag tag-C"><span class="stamp">Dobara</span><p>${esc(r.error || "Grade nahi ho paya.")}</p></div>`;
    return;
  }
  const word = { A: "Shabash!", B: "Dhyan do", C: "Oops!" }[r.grade];
  res.innerHTML = `<div class="tag tag-${r.grade}">
      <span class="stamp">${word}</span>
      <p>${esc(r.tag_hi.replace(/^(Shabash!|Oops!|Thoda dhyan do:)\s*/, ""))}</p>
      <p class="meta">${esc(r.bhawan)}, ${STREAM_NAME[r.bin_stream]} dabba: grade ${r.grade}, lagbhag ${r.contamination}% galat cheezein</p>
    </div>
    <button class="again" type="button">Agla dabba</button>`;
  res.querySelector(".again").onclick = () => {
    $("#report-form").reset();
    $("#photo-preview").hidden = true;
    $("#photo-hint").hidden = false;
    pickedStream = null;
    $("#bins").classList.remove("picked");
    document.querySelectorAll(".bin").forEach((x) => x.setAttribute("aria-pressed", "false"));
    $("#bhawan").value = store.get() || "";
    res.hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  res.scrollIntoView({ behavior: "smooth", block: "center" });
}

/* ---------- Start ---------- */
(async function init() {
  try {
    META = await api("/api/meta");
  } catch (e) {
    $("#board").innerHTML = `<li>API se connect nahi ho paya: ${esc(e.message)}</li>`;
    return;
  }
  buildForm();
  showTab(location.hash === "#report" ? "report" : "board");
})();
