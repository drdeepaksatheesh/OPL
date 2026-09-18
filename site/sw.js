const CACHE = "opl-reference-labs-v1";
const BASE = new URL("./", self.location.href).pathname;
const SHELL = [
  BASE,
  BASE + "index.html",
  BASE + "styles.css",
  BASE + "modules.json",
  BASE + "manifest.webmanifest",
  BASE + "config.js",
  BASE + "analytics.js",
  BASE + "pwa.js",
  BASE + "reference-lab-core.mjs",
  BASE + "reference-validation.mjs",
  BASE + "offline-store.mjs",
  BASE + "reference/ecg-id/index.html",
  BASE + "reference/ecg-id/styles.css",
  BASE + "reference/ecg-id/app.mjs",
  BASE + "reference/ecg-id/ideal-ecg.mjs",
  BASE + "reference/ecg-id/teaching.mjs",
  BASE + "reference/ecg-id/manifest.json",
  BASE + "icons/icon.svg"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.includes("/reference/") && url.pathname.includes("/data/")) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then(cache => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(event.request, copy));
      }
      return response;
    }))
  );
});
