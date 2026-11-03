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
  // The Console fonts are named in the stylesheet, not the page: keep them too, so the titles, numbers and text
  // keep their faces with the network off even when the first visit fetched them before this worker existed
  for (const css of files.filter((f) => f.endsWith('.css'))) {
    const text = await (await fetch(css)).text()
    files.push(...[...text.matchAll(/url\((\/assets\/[^)]+\.woff2)\)/g)].map((m) => m[1]))
  }
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

// Photos and texts waiting on the phone (src/uploads.ts saves them in IndexedDB the moment the guest presses
// «Отправить»). On Android, Background Sync wakes this worker once there is a network and it sends them, even with
// the app closed; an iPhone has no Background Sync and sends them the next time the app opens.
// Keep DB, the stores and the entry shape in step with src/uploads.ts
const DB = 'gamify-uploads'
const QUEUE = 'queue'
const META = 'meta'
const SYNC_TAG = 'uploads'
const LOCK = 'gamify-uploads'

function done(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function database() {
  const req = indexedDB.open(DB, 1)
  req.onupgradeneeded = () => {
    req.result.createObjectStore(QUEUE, { keyPath: 'id' })
    req.result.createObjectStore(META)
  }
  return done(req)
}

const inStore = (db, name, mode, run) => done(run(db.transaction(name, mode).objectStore(name)))

// The server's answer, { refused } when it said no, or { loggedOut } when it no longer knows the guest's login (the
// entry keeps its bytes and waits); no answer at all throws, so the browser tries again later
async function post(api, e, path, init) {
  const headers = { Authorization: `Bearer ${e.token}`, ...init.headers }
  const res = await fetch(api + path, { method: 'POST', ...init, headers })
  if (res.ok) return res.json()
  if (res.status === 401) return { loggedOut: true }
  if (res.status >= 500 || res.status === 408 || res.status === 429) throw new Error(`API ${res.status}`)
  const { detail } = await res.json().catch(() => ({}))
  return { refused: typeof detail === 'string' ? detail : 'error' }
}

// Both steps of one send, as the app does them, under the login of the guest who sent it
async function sendOne(db, api, e) {
  const fail = (reason) => inStore(db, QUEUE, 'readwrite', (s) => s.put({ ...e, photo: undefined, thumb: undefined, failed: reason }))
  // The phone's copy goes once the server has confirmed it
  const remove = () => inStore(db, QUEUE, 'readwrite', (s) => s.delete(e.id))
  if (!e.claimed) {
    const r = await post(api, e, `/api/tasks/${e.taskId}/claim`, {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: e.id, text: e.text }),
    })
    if (r.loggedOut) return
    if (r.refused) return fail(r.refused)
    if (r.result === 'awarded' || r.result === 'already') return remove()
    if (r.result !== 'claimed') return fail(r.result)
    e = { ...e, claimed: true }
    await inStore(db, QUEUE, 'readwrite', (s) => s.put(e))
  }
  if (!e.photo || !e.thumb) return fail('error')
  const form = new FormData()
  form.append('photo', new Blob([e.photo], { type: 'image/jpeg' }), 'photo.jpg')
  form.append('thumb', new Blob([e.thumb], { type: 'image/jpeg' }), 'thumb.jpg')
  const r = await post(api, e, `/api/claims/${e.id}/files`, { body: form })
  if (r.loggedOut) return
  return r.refused ? fail(r.refused) : remove()
}

async function sendWaiting() {
  const db = await database()
  const api = await inStore(db, META, 'readonly', (s) => s.get('api'))
  if (api === undefined) return
  try {
    // The app holds the same lock while it sends: read the queue only once it is ours, so nothing sent or changed by
    // the app meanwhile is sent again or written back
    const run = async () => {
      const waiting = (await inStore(db, QUEUE, 'readonly', (s) => s.getAll())).filter((e) => !e.failed).sort((a, b) => a.at - b.at)
      for (const e of waiting) await sendOne(db, api, e)
    }
    await (navigator.locks ? navigator.locks.request(LOCK, run) : run())
  } finally {
    // An open app shows what changed and fetches the new totals
    for (const client of await self.clients.matchAll({ type: 'window' })) client.postMessage(SYNC_TAG)
  }
}

self.addEventListener('sync', (e) => {
  if (e.tag === SYNC_TAG) e.waitUntil(sendWaiting())
})

// Pushes (piece 19): the server sends { id, sub, title, body, url }. The phone shows it, then tells the server it
// arrived, with no login: this worker can't read the app's stored login, so the push's id and its subscription key
// are what it reports. Tapping it opens the quiz's task page, or the feed
async function reportArrival(data) {
  try {
    const db = await database()
    const api = (await inStore(db, META, 'readonly', (s) => s.get('api'))) ?? ''
    await fetch(`${api}/api/push/${data.id}/received`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription: data.sub }),
    })
  } catch {
    // Not counted; the push itself was shown
  }
}

self.addEventListener('push', (e) => {
  let data
  try {
    data = e.data.json()
  } catch {
    return
  }
  e.waitUntil(Promise.all([
    self.registration.showNotification(data.title, {
      body: data.body || undefined,
      icon: '/icon-192.png',
      tag: `push-${data.id}`,
      data: { url: data.url || '/app' },
    }),
    reportArrival(data),
  ]))
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const url = new URL(e.notification.data?.url || '/app', self.location.origin).href
  e.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const app = open.find((c) => new URL(c.url).origin === self.location.origin)
    if (app) {
      await app.focus()
      return app.navigate(url).catch(() => self.clients.openWindow(url))
    }
    return self.clients.openWindow(url)
  })())
})
