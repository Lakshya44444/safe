// Kachra Report Card front end. Plain JS, no build step.
// Loaded after i18n.js (t, applyI18n, setLang, tagHi, LANG), certificate.js and offline.js.
// The API defaults to the same origin; add ?api=https://your-api.onrender.com to point elsewhere.
"use strict";

const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => root.querySelectorAll(s);

const STREAMS = ["wet", "dry", "sanitary", "special_care"];
const GRADE_COLOR = { A: "var(--pass)", B: "var(--warn)", C: "var(--pen)" };
const STREAM_COLOR = { wet: "var(--wet)", dry: "var(--dry)", sanitary: "var(--san)", special_care: "var(--spc)" };
const ISSUE_KEY = { overflow: "quick.overflow", missed_pickup: "quick.missed_pickup", broken_bin: "quick.broken_bin" };
const PLAY_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5Z"/></svg>';
const BIN_SVG = (s) => `<svg style="color:${STREAM_COLOR[s]}" aria-hidden="true"><use href="#bin"/></svg>`;
// Workers may speak Hindi, so voice autofill also understands common Hindi words.
const SPOKEN_STREAM = {
  wet: "wet", geela: "wet", gila: "wet", food: "wet", "गीला": "wet",
  dry: "dry", sookha: "dry", sukha: "dry", "सूखा": "dry",
  sanitary: "sanitary", "सैनिटरी": "sanitary",
  special: "special_care", hazardous: "special_care", dawai: "special_care", "दवाई": "special_care",
};

const letter = (score) => (score >= 80 ? "A" : score >= 60 ? "B" : "C");
const streamName = (s) => t("stream." + s);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage blocked */ } },
};

let META = null;
let pickedStream = null;
let days = 7;
let lastRanks = {};          // Bhawan -> rank on the last render, to animate moves
let highlight = null;        // Bhawan to flash after a check
let topRow = null;           // for the hero certificate

/* ---------- helpers ---------- */

class OfflineError extends Error {}

async function api(path, opts = {}, timeoutMs = 60000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let r;
  try {
    r = await fetch(API + path, { ...opts, signal: ctrl.signal });
  } catch (e) {
    if (e.name === "AbortError") throw new Error("The server took too long. Try again.");
    throw new OfflineError("No connection to the server.");
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
  const hi = LANG === "hi";
  if (m < 1) return hi ? "अभी" : "just now";
  if (m < 60) return hi ? `${m} मिनट पहले` : `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return hi ? `${h} घंटे पहले` : `${h} h ago`;
  const d = Math.round(h / 24);
  return hi ? `${d} दिन पहले` : d === 1 ? "yesterday" : `${d} days ago`;
}

function feedback(r) {
  return LANG === "hi" ? tagHi(r.grade, r.bin_stream, r.found_items || []) : r.tag;
}

function setError(msg) { $("#form-error").textContent = msg || ""; }

function showBanner(msg, ms = 6000) {
  const b = $("#banner");
  b.textContent = msg;
  b.hidden = false;
  clearTimeout(showBanner.timer);
  showBanner.timer = setTimeout(() => { b.hidden = true; }, ms);
}

function restartAnimation(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
}

/* ---------- tabs and language ---------- */

function showTab(which) {
  for (const tab of ["board", "report"]) {
    $(`#tab-${tab}`).setAttribute("aria-selected", String(tab === which));
    $(`#view-${tab}`).hidden = tab !== which;
  }
  if (which === "board") loadBoard();
  history.replaceState(null, "", (location.search || "") + (which === "report" ? "#report" : ""));
}
$("#tab-board").onclick = () => showTab("board");
$("#tab-report").onclick = () => showTab("report");
$("#lang").onclick = () => setLang(LANG === "hi" ? "en" : "hi");
let lastResult = null;       // re-rendered when the language changes
document.addEventListener("langchange", () => {
  if (META) buildBins();
  if (!$("#view-board").hidden) loadBoard();
  if (lastResult) showResult(...lastResult);
  else if (!$("#result").querySelector(".tag")) resetResult();
});

/* ---------- report card (dashboard) ---------- */

async function loadBoard() {
  let rows, sum, recent, today;
  try {
    [rows, sum, recent, today] = await Promise.all([
      api(`/api/leaderboard?days=${days}`),
      api(`/api/summary?days=${days}`),
      api("/api/reports?limit=12"),
      api("/api/summary?days=1"),
    ]);
  } catch (e) {
    $("#board").innerHTML = `<li class="row empty-row">${esc(e.message)}</li>`;
    return;
  }
  renderHero(today, sum, rows);
  renderBoard(rows);
  drawTrend($("#trend"), sum.daily);
  drawStreams(sum.by_stream);
  loadIssues();
  loadPlan();
  $("#recent").innerHTML = renderWall(recent);
}

async function loadPlan() {
  const [plan, fc] = await Promise.all([
    api("/api/collection-plan").catch(() => []),
    api("/api/forecast?days=7").catch(() => []),
  ]);
  $("#plan").innerHTML = plan.length ? plan.slice(0, 6).map((p) => {
    const why = p.reasons.map((r) => r.kind === "hazard"
      ? `⚠️ ${t("plan.hazard", { items: r.items.map((x) => (LANG === "hi" ? ITEM_HI[x] || x : x)).join(", "), bin: streamName(r.bin_stream) })}`
      : `${ISSUE_KEY[r.kind] ? t(ISSUE_KEY[r.kind]) : esc(r.kind)} · ${t("plan.hours", { h: Math.round(r.hours_open) })}`);
    if (p.mixed_bins_today) why.push(t(p.mixed_bins_today === 1 ? "plan.mixed1" : "plan.mixed", { n: p.mixed_bins_today }));
    return `<li><span class="plan-n">${p.order}</span><div><b>${esc(p.bhawan)}</b><small>${why.map(esc).join("<br>")}</small></div></li>`;
  }).join("") : `<li class="empty">${t("plan.empty")}</li>`;
  const sliding = fc.filter((f) => f.needs_nudge);
  $("#nudge").innerHTML = sliding.length ? sliding.slice(0, 6).map((f) => `
    <li><b>${esc(f.bhawan)}</b><span class="nudge-grade g-${letter(f.tomorrow)}">${letter(f.tomorrow)}</span>
      <small>${t("nudge.line", { last: f.last, tomorrow: f.tomorrow, slope: f.slope_per_day > 0 ? "+" + f.slope_per_day : f.slope_per_day })}</small>
      <button class="play-mini" data-b="${esc(f.bhawan)}" type="button">${PLAY_SVG}<span>${LANG === "hi" ? "वार्डन ब्रीफ़िंग" : "Warden briefing"}</span></button></li>`).join("")
    : `<li class="empty">${t("nudge.empty")}</li>`;
}
$("#nudge").addEventListener("click", (e) => {
  const b = e.target.closest(".play-mini");
  if (b) playBriefing(b, b.dataset.b);
});

$$(".range button").forEach((b) => b.addEventListener("click", () => {
  days = Number(b.dataset.days);
  $$(".range button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  lastRanks = {};
  loadBoard();
}));

function renderHero(today, week, rows) {
  const score = today.reports ? today.daily.at(-1)?.score : week.daily.at(-1)?.score;
  const grade = score == null ? "–" : letter(score);
  const stamp = $("#campus-grade");
  stamp.textContent = grade;
  stamp.className = `stamp-xl g-${grade}`;
  restartAnimation(stamp, "landed");
  $("#campus-score").textContent = score ?? "–";
  $("#hero-title").textContent = t(today.reports ? "hero.today" : "hero.latest");

  const weights = {};
  rows.forEach((r) => r.top_wrong_items.forEach((it, i) => { weights[it] = (weights[it] || 0) + 3 - i; }));
  let worst = Object.entries(weights).sort((x, y) => y[1] - x[1])[0]?.[0];
  topRow = rows[0] || null;
  const best = topRow?.bhawan;
  if (LANG === "hi") {
    worst = worst && (ITEM_HI[worst] || worst);
    $("#remark").textContent =
      score == null ? "अभी कोई डब्बा नहीं जाँचा गया। पहली फ़ोटो से रिपोर्ट कार्ड शुरू होगा।" :
      grade === "A" ? `बहुत बढ़िया, रुड़की!${best ? ` ${best} सबसे आगे है।` : ""}` :
      grade === "B" ? `अच्छी कोशिश।${worst ? ` ${worst} गलत डब्बे में न डालें।` : ""}` :
      `और मेहनत चाहिए।${worst ? ` गलत डब्बों में बहुत ज़्यादा ${worst} है।` : ""}`;
  } else {
    $("#remark").textContent =
      score == null ? "No bins checked yet. The first photo starts the report card." :
      grade === "A" ? `Excellent work, Roorkee.${best ? ` ${best} leads the class.` : ""}` :
      grade === "B" ? `Good effort.${worst ? ` Keep ${worst} out of the wrong bins.` : ""}` :
      `Needs work.${worst ? ` Too much ${worst} in the wrong bins.` : ""}`;
  }

  const fix = week.issues.avg_hours_to_fix;
  const wc = week.worker_checks || {};
  const hi = LANG === "hi";
  const n = week.reports.toLocaleString("en-IN");
  $("#marks").innerHTML = `
    <div class="mark"><dd>${week.segregation_rate}%</dd><dt>${hi ? "डब्बे साफ़" : "bins clean"}</dt><small>${hi ? `${n} जाँचे गए` : `${n} checked in ${week.days === 1 ? "a day" : week.days + " days"}`}</small></div>
    <div class="mark"><dd>~${week.compost_kg_estimate.toLocaleString("en-IN")} kg</dd><dt>${hi ? "खाद के लायक" : "ready for compost"}</dt><small>${hi ? "अनुमान" : "estimate"}: ${week.wet_bins_compost_ready} × ${week.kg_per_wet_bin} kg</small></div>
    <div class="mark"><dd>${week.issues.open}</dd><dt>${hi ? "खुली शिकायतें" : "open complaints"}</dt><small>${fix != null ? (hi ? `औसतन ${fix} घंटे में ठीक` : `fixed in ${fix} h on average`) : ""}</small></div>
    <div class="mark mark-hazard${(week.hazards?.bins || 0) ? " on" : ""}"><dd>${week.hazards?.bins ?? 0}</dd><dt>${t("mark.hazard")}</dt><small>${week.hazards?.top_items?.length ? esc(week.hazards.top_items.map((x) => (hi ? ITEM_HI[x] || x : x)).join(", ")) : t("mark.hazard.none")}</small></div>
    <div class="mark"><dd>~${(week.co2e_kg_avoided_estimate ?? 0).toLocaleString("en-IN")}</dd><dt>${t("mark.co2")}</dt><small>${t("mark.co2.note")}</small></div>
    <div class="mark"><dd>${wc.agreement_rate == null ? "–" : wc.agreement_rate + "%"}</dd><dt>${t("mark.agree")}</dt><small>${wc.checked ? t("mark.agree.note", { n: wc.checked }) : t("mark.agree.none")}</small></div>`;

  const cert = $("#hero-cert");
  cert.hidden = !topRow;
  if (topRow) cert.innerHTML = `<svg aria-hidden="true"><use href="#star"/></svg> ${t("hero.cert")}: ${esc(topRow.bhawan)}`;
  heroOf = rows.length;
}
let heroOf = 0;
$("#hero-cert").onclick = () => topRow && downloadCertificate({ ...topRow, of: heroOf, days });

function renderBoard(rows) {
  const board = $("#board");
  board.innerHTML = rows.length ? rows.map(boardRow).join("")
    : `<li class="row empty-row">${LANG === "hi" ? "इस समय में कोई डब्बा नहीं जाँचा गया।" : "No bins checked in this period."}</li>`;
  restartAnimation(board, "landed");

  // Rows whose rank changed slide in from where they were.
  const first = board.firstElementChild;
  const rowH = first ? first.getBoundingClientRect().height + 8 : 80;
  rows.forEach((r) => {
    const before = lastRanks[r.bhawan];
    const el = board.querySelector(`[data-bhawan="${CSS.escape(r.bhawan)}"]`);
    if (!el) return;
    if (before && before !== r.rank) {
      el.style.setProperty("--from", `${(before - r.rank) * rowH}px`);
      el.classList.add(before > r.rank ? "moved-up" : "moved-down");
    }
    if (r.bhawan === highlight) el.classList.add("flash");
  });
  highlight = null;
  lastRanks = Object.fromEntries(rows.map((r) => [r.bhawan, r.rank]));
}

function boardRow(r, i) {
  const n = r.reports || 1;
  const pct = (k) => (100 * r.grades[k]) / n;
  const g = letter(r.score);
  const hi = LANG === "hi";
  const trend = r.trend > 0 ? `<span class="trend-up">▲ ${r.trend} ${hi ? "आज" : "today"}</span>`
    : r.trend < 0 ? `<span class="trend-down">▼ ${Math.abs(r.trend)} ${hi ? "आज" : "today"}</span>` : "";
  const items = hi ? r.top_wrong_items.map((x) => ITEM_HI[x] || x) : r.top_wrong_items;
  const wrong = items.length ? (hi ? "मिला: " : "Found: ") + esc(items.join(", ")) : (hi ? "कुछ गलत नहीं मिला" : "Nothing in the wrong bin");
  return `<li class="row" style="--i:${i}" data-bhawan="${esc(r.bhawan)}" tabindex="0" aria-label="${esc(r.bhawan)}, ${r.score} of 100, grade ${g}. Open report card">
    ${i < 3 ? '<svg class="star" aria-hidden="true"><use href="#star"/></svg>' : ""}
    <div class="rank">${r.rank}</div>
    <div class="name">${esc(r.bhawan)}<small>${r.reports} ${hi ? "डब्बे जाँचे" : "bins checked"}</small></div>
    <div class="mid">
      <div class="bar" aria-hidden="true">
        <i class="a" style="width:${pct("A")}%"></i><i class="b" style="width:${pct("B")}%"></i><i class="c" style="width:${pct("C")}%"></i>
      </div>
      <div class="wrong">${wrong}</div>
    </div>
    <div class="score">${r.score}<small>/100</small>${trend}</div>
    <div class="stamp g-${g}" aria-hidden="true">${g}</div>
    <button class="play" data-play="${esc(r.bhawan)}" aria-label="Play ${esc(r.bhawan)}'s voice report">${PLAY_SVG}</button>
  </li>`;
}

function drawStreams(byStream) {
  $("#streams").innerHTML = Object.entries(byStream).map(([s, v]) => `
    <li>
      ${BIN_SVG(s)}
      <div><div class="sname">${streamName(s)}</div>
        <div class="sbar"><i style="width:${v.clean_rate ?? 0}%;background:${STREAM_COLOR[s]}"></i></div></div>
      <span class="sval">${v.clean_rate == null ? "–" : v.clean_rate + "%"}</span>
    </li>`).join("");
}

async function loadIssues() {
  const list = await api("/api/issues?status=open").catch(() => []);
  const hi = LANG === "hi";
  $("#issue-note").textContent = list.length ? (hi ? `${list.length} लगी हैं` : `${list.length} pinned`) : "";
  $("#issues").innerHTML = list.length ? list.map((i) => `
    <li>
      <b>${esc(i.bhawan)}</b>
      <div class="what">${ISSUE_KEY[i.kind] ? t(ISSUE_KEY[i.kind]) : esc(i.kind)}${i.note ? ` – ${esc(i.note)}` : ""}</div>
      <div class="meta">${timeAgo(i.created_at)}${i.reporter ? `, ${esc(i.reporter)}` : ""}</div>
      <button class="fix" data-id="${i.id}">${hi ? "ठीक हो गया" : "Mark fixed"}</button>
    </li>`).join("") : `<li class="empty">${hi ? "कोई शिकायत नहीं। सब डब्बे समय पर खाली हुए।" : "Nothing pinned. Every bin was emptied on time."}</li>`;
}
$("#report-full").onclick = () => window.openChat?.(LANG === "hi" ? "डब्बा भर गया" : "Bin is full");
document.addEventListener("issuecreated", () => { if (!$("#view-board").hidden) loadBoard(); });
$("#issues").addEventListener("click", async (e) => {
  const b = e.target.closest(".fix");
  if (!b) return;
  b.disabled = true;
  try {
    await api(`/api/issues/${b.dataset.id}/resolve`, { method: "POST" });
    loadBoard();
  } catch (err) {
    b.disabled = false;
    showBanner(err.message);
  }
});

// Photo wall: real bin photos with the grade stamped on them; note-only checks show the bin and the words.
function renderWall(reports) {
  if (!reports.length) return `<li class="tile-empty">${LANG === "hi" ? "अभी कोई जाँच नहीं।" : "No checks yet."}</li>`;
  return reports.map((r) => {
    const g = r.grade || "…";
    const color = GRADE_COLOR[r.grade] || "var(--ink-soft)";
    const media = r.photo_url
      ? `<img src="${API}${esc(r.photo_url)}" alt="${esc(r.bhawan)} ${streamName(r.bin_stream)} bin" loading="lazy">`
      : `<div class="tile-note" style="--s:${STREAM_COLOR[r.bin_stream]}">${BIN_SVG(r.bin_stream)}<q>${esc(r.note || "")}</q></div>`;
    const text = r.status === "graded" ? feedback(r) : r.status === "failed" ? (r.error || "") : "…";
    return `<li class="tile">
      <div class="tile-media">${media}<span class="tile-stamp" style="--c:${color}">${g}</span></div>
      <div class="tile-body">
        <div class="tile-title"><b>${esc(r.bhawan)}</b> <span>${streamName(r.bin_stream)}</span></div>
        <p>${esc(text)}</p>
        <span class="meta">${timeAgo(r.created_at)}</span>
      </div>
    </li>`;
  }).join("");
}

function drawTrend(svg, daily) {
  if (!daily.length) { svg.innerHTML = `<text x="24" y="100">${LANG === "hi" ? "अभी डेटा नहीं" : "No data yet"}</text>`; return; }
  const W = 640, H = 200, L = 38, R = 30, T = 22, B = 30;
  const x = (i) => L + (daily.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (daily.length - 1));
  const y = (v) => T + ((100 - v) * (H - T - B)) / 100;
  const grid = [0, 60, 80, 100].map((v) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="6" y="${y(v) + 4}">${v}</text>`).join("");
  const pts = daily.map((d, i) => `${x(i)},${y(d.score)}`);
  const area = `<path class="area" d="M${x(0)},${y(0)} L${pts.join(" L")} L${x(daily.length - 1)},${y(0)} Z"/>`;
  const dots = daily.map((d, i) => `<circle class="dot" cx="${x(i)}" cy="${y(d.score)}" r="4.5"><title>${d.date}: ${d.score} (${d.reports})</title></circle>`).join("");
  const fmt = (d) => new Date(d + "T00:00:00").toLocaleDateString(LANG === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
  const step = Math.ceil(daily.length / 8);
  const labels = daily.map((d, i) => (i % step === 0 || i === daily.length - 1)
    ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${fmt(d.date)}</text>` : "").join("");
  const last = daily.at(-1);
  svg.innerHTML = grid + area + `<polyline class="line" points="${pts.join(" ")}"/>` + dots + labels +
    `<text class="last" x="${x(daily.length - 1) - 6}" y="${y(last.score) - 12}" text-anchor="end">${last.score}</text>`;
}

// Board clicks: play the briefing, or open the Bhawan's report card.
$("#board").addEventListener("click", (e) => {
  const play = e.target.closest(".play");
  if (play) { playBriefing(play, play.dataset.play); return; }
  const row = e.target.closest(".row[data-bhawan]");
  if (row) openDetail(row.dataset.bhawan);
});
$("#board").addEventListener("keydown", (e) => {
  const row = e.target.closest(".row[data-bhawan]");
  if (row && (e.key === "Enter" || e.key === " ") && e.target === row) { e.preventDefault(); openDetail(row.dataset.bhawan); }
});

// The warden's ElevenLabs voice note, or the browser's own voice if TTS is off.
let audioEl = null;
async function playBriefing(btn, bhawan) {
  btn.setAttribute("aria-busy", "true");
  btn.disabled = true;
  try {
    const b = await api(`/api/briefing/${encodeURIComponent(bhawan)}`);
    if (b.audio_url) {
      audioEl?.pause();
      audioEl = new Audio(API + b.audio_url);
      await audioEl.play();
    } else if ("speechSynthesis" in window) {
      speechSynthesis.cancel();
      speechSynthesis.speak(Object.assign(new SpeechSynthesisUtterance(b.text), { lang: "en-IN" }));
    } else {
      showBanner(b.text, 12000);
    }
  } catch (err) {
    showBanner(err.message);
  } finally {
    btn.removeAttribute("aria-busy");
    btn.disabled = false;
  }
}

/* ---------- one Bhawan's report card (dialog) ---------- */

async function openDetail(bhawan) {
  const dlg = $("#detail");
  const body = $("#detail-body");
  body.innerHTML = `<p class="detail-loading">${esc(bhawan)}…</p>`;
  if (!dlg.open) dlg.showModal();
  let d;
  try {
    d = await api(`/api/bhawans/${encodeURIComponent(bhawan)}?days=${days}`);
  } catch (e) {
    body.innerHTML = `<p>${esc(e.message)}</p>`;
    return;
  }
  const hi = LANG === "hi";
  const g = d.score == null ? "–" : letter(d.score);
  const worst = d.worst_stream;
  const worstItems = worst ? d.by_stream[worst].top_wrong_items.map((x) => (hi ? ITEM_HI[x] || x : x)) : [];
  const advice = !worst ? "" : hi
    ? `सबसे कमज़ोर: ${streamName(worst)} डब्बा${worstItems.length ? `, इसमें ${worstItems.join(", ")} मिल रहा है।` : "।"}`
    : `Weakest: the ${streamName(worst).toLowerCase()} bin${worstItems.length ? `, where ${worstItems.join(", ")} ${worstItems.length > 1 ? "keep" : "keeps"} turning up.` : "."}`;
  const period = d.days === 1 ? (hi ? "आज" : "today") : (hi ? `${d.days} दिन` : `${d.days} days`);

  body.innerHTML = `
    <div class="d-head">
      <div class="stamp-xl g-${g} landed">${g}</div>
      <div>
        <p class="eyebrow-hand">${hi ? "रिपोर्ट कार्ड" : "Report card"}, ${period}</p>
        <h2 id="detail-name">${esc(d.bhawan)} Bhawan</h2>
        <p class="d-sub">${d.score ?? "–"}/100${d.rank ? `, ${hi ? "रैंक" : "rank"} ${d.rank} / ${d.of}` : ""}, ${d.reports} ${hi ? "डब्बे जाँचे" : "bins checked"}</p>
        <p class="remark d-remark">${esc(advice)}</p>
      </div>
    </div>
    <div class="d-actions">
      <button class="d-btn" data-act="listen">${PLAY_SVG} ${hi ? "वार्डन रिपोर्ट सुनें" : "Listen to the warden briefing"}</button>
      ${d.score != null ? `<button class="d-btn" data-act="cert"><svg aria-hidden="true"><use href="#star"/></svg> ${t("hero.cert")}</button>` : ""}
    </div>
    <div class="d-grid">
      ${STREAMS.map((s) => {
        const v = d.by_stream[s];
        const items = v.top_wrong_items.map((x) => (hi ? ITEM_HI[x] || x : x));
        return `<div class="d-bin">
          ${BIN_SVG(s)}
          <div class="d-bin-name">${streamName(s)}</div>
          <div class="d-bin-val">${v.clean_rate == null ? "–" : v.clean_rate + "%"}</div>
          <div class="d-bin-sub">${v.reports ? (hi ? `${v.reports} में से साफ़` : `clean, of ${v.reports}`) : (hi ? "कोई जाँच नहीं" : "no checks")}</div>
          ${items.length ? `<div class="d-bin-items">${esc(items.join(", "))}</div>` : ""}
        </div>`;
      }).join("")}
    </div>
    <h3>${hi ? "रोज़ का स्कोर" : "Score by day"}</h3>
    <svg class="trend" id="d-trend" viewBox="0 0 640 200" role="img" aria-label="Daily score"></svg>
    <h3>${hi ? "ताज़ा जाँच" : "Latest checks"}</h3>
    <ul class="wall">${renderWall(d.recent)}</ul>`;
  drawTrend($("#d-trend"), d.daily);
  body.querySelector('[data-act="listen"]').onclick = (e) => playBriefing(e.currentTarget, d.bhawan);
  const certBtn = body.querySelector('[data-act="cert"]');
  if (certBtn) certBtn.onclick = () => downloadCertificate({ bhawan: d.bhawan, score: d.score, rank: d.rank, of: d.of, days: d.days });
}
$("#detail-close").onclick = () => $("#detail").close();
$("#detail").addEventListener("click", (e) => { if (e.target.id === "detail") e.target.close(); });

/* ---------- check a bin ---------- */

function buildForm() {
  $("#bhawan").innerHTML = `<option value=""></option>` + META.bhawans.map((b) => `<option>${esc(b)}</option>`).join("");
  const saved = store.get("kachra.bhawan");
  if (saved && META.bhawans.includes(saved)) $("#bhawan").value = saved;
  buildBins();
  if (META.agent_id) {
    $("#agent").hidden = false;
    $("#agent-slot").innerHTML = `<elevenlabs-convai agent-id="${esc(META.agent_id)}"></elevenlabs-convai>`;
    const s = document.createElement("script");
    s.src = "https://unpkg.com/@elevenlabs/convai-widget-embed";
    s.async = true;
    document.body.appendChild(s);
  }
}

function buildBins() {
  $("#bins").innerHTML = META.streams.map((s) => `
    <button type="button" class="bin bin-${s}" data-stream="${s}" aria-pressed="${s === pickedStream}">
      <svg aria-hidden="true"><use href="#bin"/></svg>
      <b>${streamName(s)}</b><small>${t("hint." + s)}</small>
    </button>`).join("");
  $("#bins").classList.toggle("picked", Boolean(pickedStream));
  const first = $("#bhawan option[value='']");
  if (first) first.textContent = LANG === "hi" ? "अपना भवन चुनें" : "Choose your Bhawan";
}
$("#bins").addEventListener("click", (e) => {
  const b = e.target.closest(".bin");
  if (b) pickStream(b.dataset.stream);
});

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

// Sample pictures (illustrations) so the app can be tried without a bin nearby.
$$(".sample").forEach((b) => b.addEventListener("click", async () => {
  try {
    const blob = await (await fetch(b.dataset.src)).blob();
    const dt = new DataTransfer();
    dt.items.add(new File([blob], b.dataset.src.split("/").pop(), { type: "image/jpeg" }));
    $("#photo").files = dt.files;
    $("#photo").onchange();
    pickStream(b.dataset.stream);
    setError("");
  } catch (e) {
    showBanner(e.message);
  }
}));

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
    $("#mic-label").textContent = t("mic.stop");
  } catch {
    setError(t("err.mic"));
  }
};

async function onRecordingDone(stream, chunks) {
  stream.getTracks().forEach((tr) => tr.stop());
  $("#mic").setAttribute("aria-pressed", "false");
  $("#mic-label").textContent = t("mic.busy");
  const fd = new FormData();
  fd.append("audio", new Blob(chunks, { type: recorder.mimeType }), "note.webm");
  try {
    const { text } = await api("/api/transcribe", { method: "POST", body: fd });
    $("#note").value = text;
    autofillFromSpeech(text);
  } catch (err) {
    setError(err.message);
  }
  $("#mic-label").textContent = t("step.speak");
}

function browserDictation() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { setError(t("err.voice")); return; }
  const rec = new SR();
  rec.lang = LANG === "hi" ? "hi-IN" : "en-IN";
  $("#mic").setAttribute("aria-pressed", "true");
  rec.onresult = (e) => { const tx = e.results[0][0].transcript; $("#note").value = tx; autofillFromSpeech(tx); };
  rec.onend = () => $("#mic").setAttribute("aria-pressed", "false");
  rec.start();
}

// "Govind Bhawan, wet bin, plastic bag on top" fills the Bhawan and bin for the worker.
function autofillFromSpeech(text) {
  const low = text.toLowerCase();
  const b = META.bhawans.find((x) => low.includes(x.toLowerCase()));
  if (b) $("#bhawan").value = b;
  const hit = Object.keys(SPOKEN_STREAM).find((k) => low.includes(k));
  if (hit) pickStream(SPOKEN_STREAM[hit]);
}

$("#report-form").onsubmit = async (e) => {
  e.preventDefault();
  setError("");
  const bhawan = $("#bhawan").value;
  if (!bhawan) return setError(t("err.bhawan"));
  if (!pickedStream) return setError(t("err.bin"));
  if (!$("#photo").files[0] && !$("#note").value.trim()) return setError(t("err.input"));
  store.set("kachra.bhawan", bhawan);

  const fd = new FormData($("#report-form"));
  fd.set("bin_stream", pickedStream);
  const photo = $("#photo").files[0];
  if (photo) fd.set("photo", await shrinkPhoto(photo), "bin.jpg");
  const submit = $("#submit");
  submit.disabled = true;
  submit.textContent = t("submit.busy");
  try {
    // Rank before and after, so the worker sees their check move the board.
    const before = await api(`/api/leaderboard?days=${days}`).catch(() => []);
    const report = await api("/api/reports?wait=1", { method: "POST", body: fd });
    const after = await api(`/api/leaderboard?days=${days}`).catch(() => []);
    const was = before.find((r) => r.bhawan === bhawan)?.rank;
    const now = after.find((r) => r.bhawan === bhawan)?.rank;
    highlight = bhawan;
    showResult(report, was, now);
  } catch (err) {
    if (err instanceof OfflineError || !navigator.onLine) {
      try {
        await OfflineQueue.add(fd);
        showOfflineSaved();
      } catch {
        setError(err.message);
      }
    } else {
      setError(err.message);
    }
  } finally {
    submit.disabled = false;
    submit.textContent = t("submit");
  }
};

// Phone photos are 3-12 MB. Resize to 1600 px on the phone: faster upload on campus Wi-Fi,
// and the server would shrink it to that size anyway.
async function shrinkPhoto(file, maxSide = 1600) {
  if (file.size < 600 * 1024 || !("createImageBitmap" in window)) return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * scale);
    c.height = Math.round(bmp.height * scale);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file;  // unusual format: let the server handle it
  }
}

function showResult(r, was, now) {
  lastResult = [r, was, now];
  const res = $("#result");
  if (r.status !== "graded") {
    res.innerHTML = `<div class="tag g-C"><div class="tag-head"><div class="tag-word">${LANG === "hi" ? "फिर से कोशिश करें" : "Try again"}</div></div>
      <p>${esc(r.error || "The bin could not be graded.")}</p></div>`;
    return;
  }
  const message = feedback(r).replace(/^(Good job!|Oops!|Needs attention:|शाबाश!|ओह!|ध्यान दें:)\s*/, "");
  const hi = LANG === "hi";
  const ids = r.identified || (r.found_items || []).map((x) => ({ item: x, belongs: null, hazard: false }));
  const danger = ids.filter((x) => x.hazard);
  const alarm = danger.length ? `<div class="hazard"><b>⚠️ ${t("hazard.title")}</b>
      <ul>${danger.map((x) => `<li><b>${esc(hi ? ITEM_HI[x.item] || x.item : x.item)}</b>: ${esc(hi ? t("hazard.why." + hazardKey(x.why)) : x.why)}</li>`).join("")}</ul>
      <p>${t("hazard.do")}</p></div>` : "";
  const items = ids.length ? `<p class="id-head">${t("id.title")}</p><ul class="ident">${ids.map((x) => `
      <li class="${x.hazard ? "danger" : ""}"><span>${x.hazard ? "⚠️ " : ""}${esc(hi ? ITEM_HI[x.item] || x.item : x.item)}</span>
        <span class="arrow">→</span>
        ${x.belongs ? `<span class="to" style="--c:${STREAM_COLOR[x.belongs]}">${BIN_SVG(x.belongs)}${streamName(x.belongs)}</span>` : `<span class="to unsure">${t("id.unsure")}</span>`}</li>`).join("")}</ul>` : "";
  const moved = was && now && was !== now;
  const rank = now ? `<p class="rank-move ${moved ? (now < was ? "up" : "down") : ""}">${
    t(moved ? "rank.moved" : "rank.same", { b: r.bhawan, now, was })}</p>` : "";
  const share = LANG === "hi"
    ? `${r.bhawan}, ${streamName(r.bin_stream)} डब्बा। लगभग ${r.contamination}% चीज़ें दूसरे डब्बे की हैं।`
    : `${r.bhawan}, ${streamName(r.bin_stream).toLowerCase()} bin. About ${r.contamination}% of what's inside belongs in another bin.`;
  res.innerHTML = `<div class="tag g-${r.grade}">
      <div class="tag-head">
        <div class="stamp-xl g-${r.grade} landed">${r.grade}</div>
        <div class="tag-word">${t("grade." + r.grade)}</div>
      </div>
      <p>${esc(message)}</p>
      ${alarm}
      ${items}
      <p class="meta">${esc(share)}</p>
      ${rank}
    </div>
    <div class="verdict" id="verdict">${verdictHtml(r)}</div>
    <button class="again" type="button">${t("again")}</button>`;
  res.querySelector(".again").onclick = resetForm;
  wireVerdict(r);
  if (window.matchMedia("(max-width: 860px)").matches) res.scrollIntoView({ behavior: "smooth", block: "start" });
}

function hazardKey(why) {
  if (!why) return "other";
  if (why.startsWith("sharps")) return "sharps";
  if (why.includes("fire")) return "fire";
  if (why.includes("mercury")) return "mercury";
  if (why.includes("drugs")) return "drugs";
  if (why.includes("toxic")) return "toxic";
  if (why.includes("infection")) return "infection";
  return "other";
}

// Worker check: one tap to agree, or pick the right grade. The model's grade is kept for evaluation.
function verdictHtml(r) {
  if (r.verdict === "agree") return `<p class="verdict-done">✓ ${t("verdict.thanks")}</p>`;
  if (r.verdict === "disagree") return `<p class="verdict-done">✓ ${t("verdict.fixed", { g: r.grade })}</p>`;
  return `<p class="verdict-q">${t("verdict.ask")}</p>
    <div class="verdict-row"><button type="button" data-v="yes">👍 ${t("verdict.yes")}</button><button type="button" data-v="no">👎 ${t("verdict.no")}</button></div>
    <div class="verdict-pick" hidden><p>${t("verdict.pick")}</p><div class="verdict-row">${["A", "B", "C"].filter((g) => g !== r.grade)
      .map((g) => `<button type="button" class="g-${g}" data-g="${g}">${g}</button>`).join("")}</div></div>`;
}
function wireVerdict(r) {
  const box = $("#verdict");
  if (!box || r.verdict) return;
  box.onclick = async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.v === "no") { box.querySelector(".verdict-pick").hidden = false; return; }
    const body = btn.dataset.v === "yes" ? { agree: true } : { agree: false, grade: btn.dataset.g };
    box.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      const upd = await api(`/api/reports/${r.id}/verdict`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (body.agree) { lastResult[0] = upd; box.innerHTML = verdictHtml(upd); }
      else showResult(upd, lastResult[1], lastResult[2]);
    } catch (err) {
      box.querySelectorAll("button").forEach((b) => (b.disabled = false));
      showBanner(err.message);
    }
  };
}

function showOfflineSaved() {
  $("#result").innerHTML = `<div class="tag g-B"><p class="tag-word">${LANG === "hi" ? "फ़ोन में सेव" : "Saved on this phone"}</p><p>${t("offline.saved")}</p></div>
    <button class="again" type="button">${t("again")}</button>`;
  $("#result .again").onclick = resetForm;
}

function resetResult() {
  lastResult = null;
  $("#result").innerHTML = `<div class="result-empty"><div class="stamp-ghost">A</div><p>${t("result.empty")}</p></div>`;
}

function resetForm() {
  $("#report-form").reset();
  $("#photo-preview").hidden = true;
  $("#photo-hint").hidden = false;
  pickStream(null);
  $("#bhawan").value = store.get("kachra.bhawan") || "";
  resetResult();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("#quick").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const bhawan = $("#bhawan").value;
  if (!bhawan) { $("#quick-msg").textContent = t("quick.first"); return; }
  b.disabled = true;
  try {
    const r = await api("/api/issues", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ bhawan, kind: b.dataset.kind, reporter: $("#reporter").value || null }),
    });
    $("#quick-msg").textContent = LANG === "hi"
      ? `शिकायत #${r.id} दर्ज: ${r.bhawan}, ${b.textContent}।`
      : `Complaint #${r.id} logged for ${r.bhawan}: ${b.textContent}.`;
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

async function flushOffline() {
  const sent = await OfflineQueue.flush(API).catch(() => 0);
  if (sent) {
    showBanner(`${sent} ${t("offline.sent")}`);
    if (!$("#view-board").hidden) loadBoard();
  }
}
window.addEventListener("online", flushOffline);

/* ---------- start ---------- */

(async function init() {
  applyI18n();
  resetResult();
  try {
    META = await api("/api/meta");
  } catch (e) {
    $("#board").innerHTML = `<li class="row empty-row">Could not reach the server: ${esc(e.message)}</li>`;
    return;
  }
  buildForm();
  const fromQr = prefillFromLink();
  showTab(location.hash === "#report" || fromQr ? "report" : "board");
  flushOffline();
})();
