/* Farewell service worker for the site root.
   Until Nov 2026 the app lived at the root and installed a service worker here (scope "/desliza/"), which would
   otherwise keep serving the old cached app instead of the new landing page. The app now lives in app/ with
   its own service worker. When a browser that has the old one checks for updates, it gets this file, which
   deletes the old caches (everything not prefixed "app-"), unregisters itself and reloads open pages. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (!k.startsWith("app-")) await caches.delete(k);
    await self.registration.unregister();
    for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url);
  })());
});
