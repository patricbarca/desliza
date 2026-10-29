/* Service worker for Desliza la Palabra.

   The whole site is ~156 MB (5 Bibles + AI texts for every book), far too much to store up front. So:
   - App shell (page, scripts, manifest, icons): cached at install, served network-first so updates
     show up as soon as there is a connection, and from cache when offline.
   - Data (Bible JSON, ia/<lang>/<book>.json, images): cached the first time they are used, served
     stale-while-revalidate. The chosen language's Bible is cached on first load, and each book's AI
     texts once that book is opened, so whatever the reader has used works offline.
   - Google Fonts: same stale-while-revalidate, in their own cache.
   Bump VERSION when the shell list changes, and DATOS when Bible/AI files are regenerated (stale-while-revalidate
   would otherwise show the old copy once); old caches are deleted on activate. */
const VERSION = "v2", DATOS = "v2";  // v2: BSB added; ~1,500 explanations fixed in en/pt/fr/de
// "app-" prefix: the site root (landing) has its own sw.js that clears every cache NOT starting with it.
const SHELL = `app-shell-${VERSION}`, DATA = `app-datos-${DATOS}`, FONTS = "app-fuentes-v1";
const SHELL_FILES = ["./", "index.html", "timeline.js?v=3", "people.js?v=3", "manifest.json",
  "icons/icon-192.png", "icons/icon-512.png", "icons/maskable-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  const keep = new Set([SHELL, DATA, FONTS]);
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => !keep.has(k)).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function networkFirst(req) {
  const cache = await caches.open(SHELL);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    return (await cache.match(req)) || (req.mode === "navigate" && await cache.match("index.html")) || Response.error();
  }
}

async function staleWhileRevalidate(req, name) {
  const cache = await caches.open(name);
  const hit = await cache.match(req);
  const fresh = fetch(req).then(res => {
    // Opaque responses (cross-origin fonts) have status 0 but are still usable.
    if (res.ok || res.type === "opaque") cache.put(req, res.clone());
    return res;
  }).catch(() => hit || Response.error());
  return hit || fresh;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
    e.respondWith(staleWhileRevalidate(req, FONTS));
    return;
  }
  if (url.origin !== location.origin) return;
  // Data and images: large and rarely changing.
  if (/\.(json|jpg|jpeg|png|webp)$/i.test(url.pathname) && !url.pathname.endsWith("manifest.json")) {
    e.respondWith(staleWhileRevalidate(req, DATA));
    return;
  }
  // Page and scripts: always try the network first so a new version is picked up right away.
  e.respondWith(networkFirst(req));
});
