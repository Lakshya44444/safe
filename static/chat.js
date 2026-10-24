// Small helper chat: complaints from students, "which bin?", Bhawan scores. Answers come from /api/chat.
"use strict";

(function () {
  const API = (new URLSearchParams(location.search).get("api") || "").replace(/\/$/, "");
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const L = () => (typeof LANG !== "undefined" && LANG === "hi" ? "hi" : "en");
  const S = {
    en: { open: "Ask or complain", title: "Kachru · Kachra helper", ph: "Type here… e.g. bin is full at Govind", send: "Send",
          hello: "Hi, I'm Kachru! Is a bin full or was pickup missed? Tell me the Bhawan and I'll put it on the notice board. You can also ask which bin something goes in.",
          chips: ["Bin is full", "Pickup missed", "Where does a battery go?", "Top Bhawan this week"], err: "Could not reach the server. Try again." },
    hi: { open: "पूछें या शिकायत करें", title: "कचरू · कचरा सहायक", ph: "यहाँ लिखें… जैसे गोविंद में डब्बा भर गया", send: "भेजें",
          hello: "नमस्ते, मैं कचरू हूँ! डब्बा भर गया या कूड़ा नहीं उठा? भवन का नाम बताइए, मैं नोटिस बोर्ड पर लगा दूँगा। आप यह भी पूछ सकते हैं कि कौन सी चीज़ किस डब्बे में जाती है।",
          chips: ["डब्बा भर गया", "कूड़ा नहीं उठा", "बैटरी कहाँ डालें?", "इस हफ़्ते सबसे अच्छा भवन"], err: "सर्वर से जुड़ नहीं पाए। फिर कोशिश करें।" },
  };
  let ctx = null;
  let greeted = false;

  const fab = el("button", "chat-fab");
  fab.type = "button";
  // "Kachru", a friendly bin mascot (original drawing): big enough to spot and tap.
  fab.innerHTML = `<span class="fab-bubble"></span>
    <svg class="mascot" viewBox="0 0 80 88" aria-hidden="true">
      <ellipse cx="40" cy="84" rx="24" ry="4" fill="rgba(0,0,0,.18)"/>
      <path d="M14 26h52l-5 52a6 6 0 0 1-6 5H25a6 6 0 0 1-6-5Z" fill="#2e8b57"/>
      <path d="M22 34h4l2 40h-4ZM54 34h4l-2 40h-4Z" fill="rgba(255,255,255,.18)"/>
      <rect x="8" y="16" width="64" height="12" rx="6" fill="#1f6f43"/>
      <rect x="31" y="8" width="18" height="10" rx="5" fill="#1f6f43"/>
      <circle cx="30" cy="48" r="7" fill="#fff"/><circle cx="50" cy="48" r="7" fill="#fff"/>
      <circle class="eye" cx="31.5" cy="49" r="3.4" fill="#1d2a4b"/><circle class="eye" cx="51.5" cy="49" r="3.4" fill="#1d2a4b"/>
      <circle cx="22" cy="58" r="3.5" fill="#ff9aa2" opacity=".8"/><circle cx="58" cy="58" r="3.5" fill="#ff9aa2" opacity=".8"/>
      <path d="M32 60q8 8 16 0" stroke="#1d2a4b" stroke-width="3" fill="none" stroke-linecap="round"/>
      <path d="M66 44q10-6 8-16" stroke="#2e8b57" stroke-width="5" fill="none" stroke-linecap="round" class="wave"/>
    </svg>`;
  fab.setAttribute("aria-label", "Chat");
  const panel = el("section", "chat-panel");
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Chat");
  panel.innerHTML = `<header><b></b><button type="button" class="chat-x" aria-label="Close">×</button></header>
    <div class="chat-log" aria-live="polite"></div><div class="chat-chips"></div>
    <form class="chat-form"><input type="text" maxlength="500" autocomplete="off"><button type="submit"></button></form>`;
  document.body.append(fab, panel);
  const log = panel.querySelector(".chat-log");
  const chips = panel.querySelector(".chat-chips");
  const input = panel.querySelector("input");

  function label() {
    const s = S[L()];
    fab.querySelector(".fab-bubble").textContent = s.open;
    panel.querySelector("header b").textContent = s.title;
    panel.querySelector(".chat-form button").textContent = s.send;
    input.placeholder = s.ph;
  }
  function bubble(text, who) {
    const b = el("div", "msg " + who, text);
    log.append(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }
  function setChips(list) {
    chips.innerHTML = "";
    list.forEach((c) => { const b = el("button", "chip", c); b.type = "button"; b.onclick = () => send(c); chips.append(b); });
  }
  async function send(text) {
    text = text.trim();
    if (!text) return;
    bubble(text, "me");
    input.value = "";
    setChips([]);
    const wait = bubble("…", "bot");
    try {
      const r = await fetch(API + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, lang: L(), context: ctx }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error);
      wait.textContent = d.say;
      ctx = d.context || null;
      setChips(d.choices?.length ? d.choices : (ctx ? [] : S[L()].chips));
      if (d.action === "issue_created") document.dispatchEvent(new CustomEvent("issuecreated"));
    } catch (e) {
      wait.textContent = S[L()].err;
      setChips(S[L()].chips);
    }
  }
  function open(prefill) {
    panel.hidden = false;
    fab.hidden = true;
    if (!greeted) { bubble(S[L()].hello, "bot"); setChips(S[L()].chips); greeted = true; }
    if (prefill) send(prefill);
    else input.focus();
  }
  function close() { panel.hidden = true; fab.hidden = false; fab.focus(); }

  fab.onclick = () => open();
  panel.querySelector(".chat-x").onclick = close;
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  panel.querySelector(".chat-form").onsubmit = (e) => { e.preventDefault(); send(input.value); };
  document.addEventListener("langchange", label);
  window.openChat = open;
  label();
})();
