// Offline support: registers the service worker and keeps reports made without network
// in IndexedDB until the phone is back online, then sends them.
"use strict";

const OfflineQueue = (() => {
  const DB = "kachra", STORE = "pending";

  function open() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function tx(mode, fn) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const out = fn(t.objectStore(STORE));
      t.oncomplete = () => resolve(out?.result ?? out);
      t.onerror = () => reject(t.error);
    });
  }

  // Store the form fields and the photo blob.
  async function add(formData) {
    const fields = {};
    let photo = null;
    for (const [k, v] of formData.entries()) {
      if (v instanceof Blob) { if (v.size) photo = { blob: v, name: v.name || "bin.jpg" }; }
      else fields[k] = v;
    }
    await tx("readwrite", (s) => s.add({ fields, photo, savedAt: Date.now() }));
  }

  async function all() { return tx("readonly", (s) => s.getAll()); }
  async function remove(id) { return tx("readwrite", (s) => s.delete(id)); }

  // Send everything queued. Returns how many were sent.
  async function flush(apiBase = "") {
    if (!navigator.onLine || !("indexedDB" in window)) return 0;
    let sent = 0;
    for (const item of await all()) {
      const fd = new FormData();
      Object.entries(item.fields).forEach(([k, v]) => fd.append(k, v));
      if (item.photo) fd.append("photo", item.photo.blob, item.photo.name);
      try {
        const r = await fetch(apiBase + "/api/reports", { method: "POST", body: fd });
        if (r.ok || (r.status >= 400 && r.status < 500 && r.status !== 429)) {
          await remove(item.id);  // sent, or rejected for good: don't retry forever
          if (r.ok) sent += 1;
        }
      } catch { break; }  // still offline
    }
    return sent;
  }

  return { add, all, flush };
})();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
