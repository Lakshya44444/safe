// English / Hindi strings. Elements carry data-i18n="key" (text) or data-i18n-ph="key" (placeholder).
"use strict";

const I18N = {
  en: {
    "brand.sub": "Every IIT Roorkee Bhawan, graded daily",
    "tab.board": "Report card",
    "tab.check": "Check a bin",
    "lang.switch": "हिंदी",
    "hero.today": "Campus grade, today",
    "hero.latest": "Campus grade, latest day",
    "hero.cert": "Certificate",
    "board.title": "Bhawan ranking",
    "range.today": "Today", "range.7": "7 days", "range.30": "30 days",
    "legend.a": "clean", "legend.b": "slightly mixed", "legend.c": "mixed",
    "legend.note": "Grade: A ≥ 80, B ≥ 60, C below",
    "trend.title": "Campus score by day",
    "streams.title": "Which bins stay clean",
    "notes.title": "Notice board", "notes.report": "Report a full bin",
    "feed.title": "Latest checks",
    "step.bhawan": "Bhawan",
    "step.bin": "Which bin?",
    "step.photo": "Photo of the bin, from above",
    "sample.try": "No bin nearby? Try a sample picture:", "sample.1": "Wet, clean", "sample.2": "Wet, with plastic", "sample.3": "Dry, with food",
    "step.camera": "Tap to open the camera",
    "step.note": "Anything to add?",
    "step.optional": "optional",
    "step.speak": "Speak",
    "ph.note": "plastic bag in the wet bin",
    "ph.name": "Your name (optional)",
    "submit": "Check this bin",
    "submit.busy": "Marking…",
    "result.empty": "The grade appears here, stamped, in about five seconds.",
    "quick.title": "Something else wrong?",
    "quick.body": "Pick the Bhawan first, then tap. It goes straight to the notice board.",
    "quick.overflow": "Bin is full", "quick.missed_pickup": "Pickup missed", "quick.broken_bin": "Bin is broken",
    "agent.title": "Or just talk",
    "agent.body": "Say the Bhawan, the bin and what you see. The voice agent logs it.",
    "foot.rules": "Graded against India's Solid Waste Management Rules 2026: wet, dry, sanitary and special care. A bin is A when up to 10% of what's inside belongs elsewhere, B up to 35%, C beyond that.",
    "foot.qr": "Print QR stickers for the bins",
    "plan.title": "Collection order today", "plan.note": "complaints first, then mixed bins",
    "plan.empty": "Nothing urgent. Follow the usual round.",
    "plan.mixed": "{n} mixed bins to re-sort", "plan.mixed1": "1 mixed bin to re-sort",
    "plan.hours": "{h} h open",
    "nudge.title": "Needs a nudge", "nudge.note": "trend over the last 7 days",
    "nudge.empty": "No Bhawan is sliding. Needs 3 days of checks per Bhawan to judge.",
    "nudge.line": "{last} today, heading to ~{tomorrow} tomorrow ({slope}/day)",
    "nudge.steady": "Steady or improving",
    "foot.report": "Monthly SWM compliance report",
    "mark.co2": "kg CO₂e avoided", "mark.co2.note": "estimate, EPA WARM factor",
    "mark.agree": "AI agrees with workers", "mark.agree.none": "no worker checks yet",
    "mark.agree.note": "{n} grades checked by workers",
    "verdict.ask": "Is this grade right?", "verdict.yes": "Yes, correct", "verdict.no": "No",
    "verdict.pick": "What grade should it be?",
    "verdict.thanks": "Thanks. Your check is counted.",
    "verdict.fixed": "Corrected to {g}. The Bhawan's score uses your grade.",
    "stream.wet": "Wet", "stream.dry": "Dry", "stream.sanitary": "Sanitary", "stream.special_care": "Special care",
    "hint.wet": "food, peels, tea leaves", "hint.dry": "plastic, paper, bottles",
    "hint.sanitary": "diapers, pads", "hint.special_care": "medicines, bulbs, batteries",
    "grade.A": "Good job!", "grade.B": "Needs attention", "grade.C": "Oops!",
    "err.bhawan": "Choose your Bhawan.", "err.bin": "Choose which bin this is.",
    "err.input": "Take a photo of the bin or add a note.",
    "err.mic": "Microphone permission was not given. Type the note instead.",
    "err.voice": "Voice input isn't available in this browser. Type the note instead.",
    "mic.stop": "Tap to stop", "mic.busy": "Transcribing…",
    "quick.first": "Choose your Bhawan above first.",
    "again": "Check the next bin",
    "offline.saved": "No internet. Saved on this phone; it will be sent by itself when the network is back.",
    "offline.sent": "reports sent that were saved offline.",
    "rank.moved": "{b} is now rank {now} (was {was}).",
    "rank.same": "{b} stays at rank {now}.",
  },
  hi: {
    "brand.sub": "IIT रुड़की के हर भवन का रोज़ का रिपोर्ट कार्ड",
    "tab.board": "रिपोर्ट कार्ड",
    "tab.check": "डब्बा जाँचें",
    "lang.switch": "English",
    "hero.today": "आज कैंपस का ग्रेड",
    "hero.latest": "कैंपस का ग्रेड, पिछला दिन",
    "hero.cert": "सर्टिफ़िकेट",
    "board.title": "भवन रैंकिंग",
    "range.today": "आज", "range.7": "7 दिन", "range.30": "30 दिन",
    "legend.a": "साफ़", "legend.b": "थोड़ा मिला हुआ", "legend.c": "मिला हुआ",
    "legend.note": "ग्रेड: A ≥ 80, B ≥ 60, C उससे कम",
    "trend.title": "रोज़ का कैंपस स्कोर",
    "streams.title": "कौन से डब्बे साफ़ रहते हैं",
    "notes.title": "नोटिस बोर्ड", "notes.report": "भरे डब्बे की शिकायत",
    "feed.title": "ताज़ा जाँच",
    "step.bhawan": "भवन",
    "step.bin": "कौन सा डब्बा?",
    "step.photo": "डब्बे की ऊपर से फ़ोटो",
    "sample.try": "पास में डब्बा नहीं? सैंपल तस्वीर आज़माएँ:", "sample.1": "गीला, साफ़", "sample.2": "गीला, प्लास्टिक के साथ", "sample.3": "सूखा, खाने के साथ",
    "step.camera": "कैमरा खोलने के लिए दबाएँ",
    "step.note": "कुछ और बताना है?",
    "step.optional": "ज़रूरी नहीं",
    "step.speak": "बोलें",
    "ph.note": "गीले डब्बे में पॉलिथीन है",
    "ph.name": "आपका नाम (ज़रूरी नहीं)",
    "submit": "डब्बा जाँचें",
    "submit.busy": "जाँच हो रही है…",
    "result.empty": "ग्रेड यहाँ मोहर के साथ लगभग पाँच सेकंड में आएगा।",
    "quick.title": "कोई और दिक्कत?",
    "quick.body": "पहले ऊपर भवन चुनें, फिर दबाएँ। शिकायत सीधे नोटिस बोर्ड पर जाएगी।",
    "quick.overflow": "डब्बा भर गया", "quick.missed_pickup": "गाड़ी नहीं आई", "quick.broken_bin": "डब्बा टूटा है",
    "agent.title": "या सीधे बोलें",
    "agent.body": "भवन, डब्बा और अंदर क्या है, बोलें। वॉइस एजेंट रिपोर्ट दर्ज कर देगा।",
    "foot.rules": "ठोस अपशिष्ट प्रबंधन नियम 2026 के चार डब्बे: गीला, सूखा, सैनिटरी, स्पेशल केयर। 10% तक गलत चीज़ें हों तो A, 35% तक B, उससे ज़्यादा C।",
    "foot.qr": "डब्बों के लिए QR स्टिकर प्रिंट करें",
    "plan.title": "आज कूड़ा उठाने का क्रम", "plan.note": "पहले शिकायतें, फिर मिले-जुले डब्बे",
    "plan.empty": "कुछ ज़रूरी नहीं। रोज़ का रास्ता लें।",
    "plan.mixed": "{n} मिले-जुले डब्बे दोबारा छाँटने हैं", "plan.mixed1": "1 मिला-जुला डब्बा दोबारा छाँटना है",
    "plan.hours": "{h} घंटे से खुली",
    "nudge.title": "इन्हें याद दिलाएँ", "nudge.note": "पिछले 7 दिनों का रुझान",
    "nudge.empty": "कोई भवन नीचे नहीं जा रहा। हर भवन के 3 दिन के आँकड़े चाहिए।",
    "nudge.line": "आज {last}, कल लगभग {tomorrow} ({slope}/दिन)",
    "nudge.steady": "स्थिर या सुधार",
    "foot.report": "मासिक SWM अनुपालन रिपोर्ट",
    "mark.co2": "kg CO₂e बचा", "mark.co2.note": "अनुमान, EPA WARM गुणांक",
    "mark.agree": "AI और कर्मचारी सहमत", "mark.agree.none": "अभी कोई जाँच नहीं",
    "mark.agree.note": "{n} ग्रेड कर्मचारियों ने जाँचे",
    "verdict.ask": "क्या यह ग्रेड सही है?", "verdict.yes": "हाँ, सही", "verdict.no": "नहीं",
    "verdict.pick": "सही ग्रेड क्या होना चाहिए?",
    "verdict.thanks": "धन्यवाद। आपकी जाँच गिनी गई।",
    "verdict.fixed": "{g} कर दिया। भवन का स्कोर आपका ग्रेड लेगा।",
    "stream.wet": "गीला", "stream.dry": "सूखा", "stream.sanitary": "सैनिटरी", "stream.special_care": "स्पेशल केयर",
    "hint.wet": "खाना, छिलके, चाय पत्ती", "hint.dry": "प्लास्टिक, कागज़, बोतल",
    "hint.sanitary": "डायपर, पैड", "hint.special_care": "दवाई, बल्ब, बैटरी",
    "grade.A": "शाबाश!", "grade.B": "ध्यान दें", "grade.C": "ओह!",
    "err.bhawan": "अपना भवन चुनें।", "err.bin": "कौन सा डब्बा है, चुनें।",
    "err.input": "डब्बे की फ़ोटो लें या कुछ लिखें।",
    "err.mic": "माइक की अनुमति नहीं मिली। नोट लिख दें।",
    "err.voice": "इस ब्राउज़र में बोलकर लिखना नहीं चलता। नोट लिख दें।",
    "mic.stop": "रोकने के लिए दबाएँ", "mic.busy": "समझ रहा है…",
    "quick.first": "पहले ऊपर अपना भवन चुनें।",
    "again": "अगला डब्बा जाँचें",
    "offline.saved": "इंटरनेट नहीं है। रिपोर्ट फ़ोन में सेव है, नेटवर्क आते ही अपने आप चली जाएगी।",
    "offline.sent": "ऑफ़लाइन सेव रिपोर्ट भेज दी गईं।",
    "rank.moved": "{b} अब रैंक {now} पर है (पहले {was})।",
    "rank.same": "{b} रैंक {now} पर बना हुआ है।",
  },
};

// Hindi names for the wrong items the model most often reports (it answers in English).
const ITEM_HI = {
  "plastic bag": "पॉलिथीन", "plastic": "प्लास्टिक", "bottle": "बोतल", "chips packet": "चिप्स का पैकेट",
  "wrapper": "रैपर", "food scraps": "खाना", "food": "खाना", "food waste": "खाना", "paper": "कागज़",
  "paper cups": "कागज़ के कप", "cardboard": "गत्ता", "sanitary pad": "पैड", "diaper": "डायपर",
  "medicine strip": "दवाई की पत्ती", "battery": "बैटरी", "bulb": "बल्ब", "glass": "कांच",
  "metal can": "डिब्बा", "vegetable peels": "छिलके", "thermocol plates": "थर्मोकोल प्लेट",
};
const BIN_HI_CONTENTS = {
  wet: "खाना, छिलके और चाय पत्ती", dry: "प्लास्टिक, कागज़, धातु और कांच",
  sanitary: "डायपर और पैड", special_care: "दवाई, बल्ब, बैटरी और पेंट",
};

let LANG = (() => {
  try { return localStorage.getItem("kachra.lang") || (navigator.language.startsWith("hi") ? "hi" : "en"); }
  catch { return "en"; }
})();

function t(key, vars = {}) {
  const s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.en[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
}

function applyI18n(root = document) {
  document.documentElement.lang = LANG === "hi" ? "hi" : "en";
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
}

function setLang(lang) {
  LANG = lang;
  try { localStorage.setItem("kachra.lang", lang); } catch { /* storage blocked */ }
  applyI18n();
  document.dispatchEvent(new CustomEvent("langchange"));
}

// The feedback tag in Hindi, built from the same grade, bin and items as the English one.
function tagHi(grade, stream, items) {
  // Oblique case after "में": गीला डब्बा -> गीले डब्बे में
  const OBL = { wet: "गीले डब्बे", dry: "सूखे डब्बे", sanitary: "सैनिटरी डब्बे", special_care: "स्पेशल केयर डब्बे" };
  if (grade === "A") return `शाबाश! ${t("stream." + stream)} डब्बा बिल्कुल साफ़ है। ऐसे ही रखें।`;
  const found = items.length ? items.slice(0, 3).map((i) => ITEM_HI[i] || i).join(", ") : "दूसरे डब्बों की चीज़ें";
  const lead = grade === "B" ? "ध्यान दें:" : "ओह!";
  return `${lead} ${OBL[stream]} में ये भी है: ${found}। इसमें सिर्फ़ ${BIN_HI_CONTENTS[stream]} डालें।`;
}
