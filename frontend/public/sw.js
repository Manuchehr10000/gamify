// Keeps the app's own files so /app opens with the network off; the last feed itself is kept by the app.
// Network first, so a new release is picked up as soon as there is a connection.
const CACHE = 'app-v1'

// On install, keep the app page and the scripts and styles it names: the first visit loads them before
// this worker exists, so without this a reload with no network would have nothing to show
async function keepApp() {
  const cache = await caches.open(CACHE)
  const page = await fetch('/', { cache: 'no-store' })
  const html = await page.clone().text()
  const files = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])
  await cache.put('/', page)
  await cache.addAll(files)
}

self.addEventListener('install', (e) => e.waitUntil(keepApp().then(() => self.skipWaiting())))
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

self.addEventListener('fetch', (e) => {
  const req = e.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(req, copy))
        }
        return res
      })
      .catch(async () => {
        const hit = await caches.match(req)
        if (hit) return hit
        // Any page of the app is the same index.html
        if (req.mode === 'navigate') return (await caches.match('/')) ?? Response.error()
        return Response.error()
      }),
  )
})
