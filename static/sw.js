// Service worker: the app shell works offline; API reads fall back to the last copy.
const VERSION = "kachra-v3";
const SHELL = ["./", "index.html", "styles.css", "app.js", "i18n.js", "certificate.js", "offline.js",
               "manifest.webmanifest", "icons/icon.svg", "icons/icon-192.png", "icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;               // reports are queued by the page, not here
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;     // fonts and CDNs: browser default

  if (url.pathname.startsWith("/api/")) {
    // Network first so the board is live; last good copy when offline.
    e.respondWith(fetch(req).then((res) => {
      if (res.ok && !url.pathname.startsWith("/api/audio/")) {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req)));
    return;
  }
  // App shell: network first so a new deploy shows up at once; cached copy when offline.
  e.respondWith(fetch(req).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req).then((hit) => hit || caches.match("index.html"))));
});
