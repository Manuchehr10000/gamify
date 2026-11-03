import { useSyncExternalStore } from 'react'
import { api, API_URL, ApiError, tokens } from './api'
import { cache, type Award, type Task } from './feed'

// Photos and texts on their way to the server. Each one is saved on the phone (IndexedDB) the moment the guest
// presses «Отправить», so closing the app loses nothing: sending resumes when the app opens again, and on Android
// the service worker (public/sw.js) may finish it with the app closed. Two steps: a small claim with the phone's
// submission ID, which the server checks and times; then the photo and its thumbnail.
export type Upload =
  // «Ждёт сети — ещё не засчитано»: the claim hasn't reached the server
  | { state: 'unclaimed' }
  // «Загружается»: the claim or the files are on their way right now
  | { state: 'sending' }
  // «Ждёт сети»: the place is held, the photo waits for the network
  | { state: 'claimed' }
  | { state: 'failed'; reason: string }
  | { state: 'sent'; award: Award }

// What the server says to a claim: claimed (place held, send the files) · awarded · already · or why it can't count
type ClaimResult = { result: 'claimed' | 'awarded' | 'already' | 'stage_closed' | 'time_up' | 'limit'; task: Task }

// One send waiting on the phone. The service worker reads the same database: keep DB, the stores and this shape in
// step with public/sw.js. Bytes as ArrayBuffer: older iPhones can't keep a Blob in IndexedDB
type Entry = {
  id: string
  // The login of the guest who sent it, so it is paid to them even if someone else signs in on this phone later
  token: string
  taskId: number
  text: string
  photo?: ArrayBuffer
  thumb?: ArrayBuffer
  claimed: boolean
  // Why the server refused it; the bytes are dropped then and the card says why until the guest has seen it
  failed?: string
  at: number
}

const DB = 'gamify-uploads'
const QUEUE = 'queue'
// The API's address: a service worker can't read the build's settings (each entry carries its guest's token)
const META = 'meta'
const SYNC_TAG = 'uploads'
// Held by whoever is sending, the app or the service worker, so the two never send or rewrite the same entry at once
const LOCK = 'gamify-uploads'

// The phone redraws photos to this before sending (dropping location and camera data); the server refuses bigger
const MAX_SIDE = 1600
const MAX_BYTES = 1024 * 1024
const THUMB_SIDE = 400
const THUMB_MAX_BYTES = 100 * 1024
// Up to this many waiting sends when the feed hasn't said the admin's number yet
const QUEUE_SIZE = 5
// After a try that got no answer: 5 s, 15 s, 30 s, 60 s, then every 5 minutes
const RETRY_MS = [5_000, 15_000, 30_000, 60_000, 300_000]
// A slow cell can take a while for a 1 MB photo; each try that timed out gets twice the time
const CLAIM_TIMEOUT_MS = 30_000
const FILES_TIMEOUT_MS = 60_000
const FILES_TIMEOUT_MAX_MS = 8 * 60_000

// ---------------------------------------------------------------- the phone's copy

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

let opening: Promise<IDBDatabase> | null = null

function database(): Promise<IDBDatabase> {
  opening ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(QUEUE, { keyPath: 'id' })
      req.result.createObjectStore(META)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  return opening
}

// Storage can be blocked (some private modes): then the sends live in memory only, as before this piece
const memory = new Map<string, Entry>()

async function inStore<T>(name: string, mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database()
  return request(run(db.transaction(name, mode).objectStore(name)))
}

const store = {
  all: () => inStore<Entry[]>(QUEUE, 'readonly', (s) => s.getAll()).catch(() => [...memory.values()]),
  put: (e: Entry) => inStore(QUEUE, 'readwrite', (s) => s.put(e)).then(() => {}, () => void memory.set(e.id, e)),
  remove: (id: string) => inStore(QUEUE, 'readwrite', (s) => s.delete(id)).then(() => {}, () => void memory.delete(id)),
}

function mirror() {
  void inStore(META, 'readwrite', (s) => s.put(API_URL, 'api')).catch(() => {})
}

// The signed-in guest's own sends: the only ones their cards show and their queue counts
const mine = (entries: Entry[]) => entries.filter((e) => e.token === tokens.get('guest'))

// ---------------------------------------------------------------- what the cards show

let views = new Map<number, Upload>()
const sent = new Map<number, Award>()
let inFlight: string | null = null
const listeners = new Set<() => void>()
const sentListeners = new Set<() => void>()

const waiting = (entries: Entry[]) => entries.filter((e) => !e.failed).sort((a, b) => a.at - b.at)

// Unchanged views keep their object, so a card doesn't redraw for nothing
const keep = (old: Upload | undefined, view: Upload) => (old && JSON.stringify(old) === JSON.stringify(view) ? old : view)

async function refresh() {
  const next = new Map<number, Upload>()
  for (const e of mine(await store.all()).sort((a, b) => a.at - b.at)) {
    const view: Upload = e.failed
      ? { state: 'failed', reason: e.failed }
      : e.id === inFlight ? { state: 'sending' } : { state: e.claimed ? 'claimed' : 'unclaimed' }
    next.set(e.taskId, keep(views.get(e.taskId), view))
  }
  sent.forEach((award, taskId) => {
    if (!next.has(taskId)) next.set(taskId, keep(views.get(taskId), { state: 'sent', award }))
  })
  views = next
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// Called whenever a send goes through, so the feed can fetch the new totals
export function onSent(listener: () => void) {
  sentListeners.add(listener)
  return () => {
    sentListeners.delete(listener)
  }
}

// Saved on the phone and not through yet, in either step
export const isWaiting = (upload: Upload | null) =>
  upload?.state === 'unclaimed' || upload?.state === 'claimed' || upload?.state === 'sending'

export function useUpload(taskId: number): Upload | null {
  return useSyncExternalStore(subscribe, () => views.get(taskId) ?? null)
}

// Forget a finished send once its result was shown; the server's task says «Выполнено» from then on
export function forgetUpload(taskId: number) {
  const u = views.get(taskId)
  if (!u || (u.state !== 'sent' && u.state !== 'failed')) return
  sent.delete(taskId)
  void store.all()
    .then((entries) => Promise.all(mine(entries).filter((e) => e.taskId === taskId && e.failed).map((e) => store.remove(e.id))))
    .then(refresh)
}

// ---------------------------------------------------------------- sending

// No real answer from the server: the proxy, a restart or overload, not a refusal of what was sent. A 401 isn't a
// refusal either: the login is the problem, not the photo, so the entry keeps its bytes and waits
const refused = (err: unknown): err is ApiError =>
  err instanceof ApiError && err.status < 500 && ![401, 408, 429].includes(err.status)
const loggedOut = (err: unknown) => err instanceof ApiError && err.status === 401

const reasonOf = (err: ApiError) => (typeof err.detail === 'string' ? err.detail : 'error')

async function finish(e: Entry, r: ClaimResult) {
  const award: Award = { result: r.result === 'already' ? 'already' : 'awarded', task: r.task }
  // The feed's copy on the phone shows «Выполнено» at once, even if the next feed load fails
  const feed = cache.feed()
  if (feed) cache.saveFeed({ ...feed, tasks: feed.tasks.map((t) => (t.id === e.taskId ? award.task : t)) })
  sent.set(e.taskId, award)
  // The phone's copy goes once the server has confirmed it
  await store.remove(e.id)
  sentListeners.forEach((l) => l())
}

async function fail(e: Entry, reason: string) {
  await store.put({ ...e, photo: undefined, thumb: undefined, failed: reason })
}

let attempt = 0

// One send, both steps, under the login of the guest who sent it. Throws when there was no answer, so the queue tries
// again later
async function step(e: Entry) {
  const token = e.token
  if (!e.claimed) {
    let r: ClaimResult
    try {
      r = await api<ClaimResult>(`/api/tasks/${e.taskId}/claim`, {
        token, json: { id: e.id, text: e.text }, timeoutMs: CLAIM_TIMEOUT_MS,
      })
    } catch (err) {
      if (refused(err)) return fail(e, reasonOf(err))
      throw err
    }
    if (r.result === 'awarded' || r.result === 'already') return finish(e, r)
    if (r.result !== 'claimed') return fail(e, r.result)
    e = { ...e, claimed: true }
    await store.put(e)
    await refresh()
  }
  if (!e.photo || !e.thumb) return fail(e, 'error')
  // A FormData can't be sent twice on every browser: built for each try
  const form = new FormData()
  form.append('photo', new Blob([e.photo], { type: 'image/jpeg' }), 'photo.jpg')
  form.append('thumb', new Blob([e.thumb], { type: 'image/jpeg' }), 'thumb.jpg')
  try {
    const timeoutMs = Math.min(FILES_TIMEOUT_MS * 2 ** attempt, FILES_TIMEOUT_MAX_MS)
    await finish(e, await api<ClaimResult>(`/api/claims/${e.id}/files`, { token, form, timeoutMs }))
  } catch (err) {
    if (refused(err)) return fail(e, reasonOf(err))
    throw err
  }
}

let running = false
let timer: ReturnType<typeof setTimeout> | undefined

// Only one sender at a time; without the Web Locks API (older browsers) the app sends alone
function exclusive(run: () => Promise<void>): Promise<void> {
  return navigator.locks ? navigator.locks.request(LOCK, run) : run()
}

// Send what waits, oldest first, each under its own guest's login. Without an answer, wait and try again on the retry
// schedule. A send whose login the server no longer knows is passed over and waits; it never blocks the others
async function drain() {
  if (running) return
  running = true
  clearTimeout(timer)
  try {
    let waitLonger = false
    await exclusive(async () => {
      // Read inside the lock: the service worker may have sent or changed entries meanwhile
      const passed = new Set<string>()
      for (;;) {
        const [next] = waiting(await store.all()).filter((e) => !passed.has(e.id))
        if (!next) return
        inFlight = next.id
        await refresh()
        try {
          await step(next)
          attempt = 0
        } catch (err) {
          if (!loggedOut(err)) throw err
          passed.add(next.id)
          waitLonger = true
        }
      }
    })
    if (!waitLonger) {
      attempt = 0
      return
    }
    throw new Error('logged out')
  } catch {
    timer = setTimeout(drain, RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)])
    attempt += 1
  } finally {
    inFlight = null
    running = false
    await refresh()
  }
}

// Opening the app, the network coming back or the app coming back to the screen: try at once, schedule from the start
function now() {
  attempt = 0
  void drain()
}

// Background Sync (Android): the service worker sends what waits once there is a network, even with the app closed
function registerSync() {
  if (!('serviceWorker' in navigator)) return
  type SyncRegistration = ServiceWorkerRegistration & { sync?: { register: (tag: string) => Promise<void> } }
  navigator.serviceWorker.getRegistration()
    .then((reg) => (reg as SyncRegistration | undefined)?.sync?.register(SYNC_TAG))
    .catch(() => {})
}

// One key per send, repeated on its retries: the server pays it once and tells a late retry of a photo a moderator
// sent back from the guest sending the same photo or text again
// (crypto.randomUUID needs https, and a phone on the venue's network may open the app over plain http)
const submissionId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

// Save the send on the phone and start sending it. false: the queue is full and nothing was saved
export async function send(taskId: number, text: string, files?: { photo: Blob; thumb: Blob }): Promise<boolean> {
  const token = tokens.get('guest')
  // Signed out: the feed sends the guest back to sign in
  if (!token) return true
  const limit = cache.feed()?.queue_size ?? QUEUE_SIZE
  const queued = waiting(mine(await store.all()))
  // This task is already on its way: a second tap saves nothing
  if (queued.some((e) => e.taskId === taskId)) return true
  if (queued.length >= limit) return false
  await store.put({
    id: submissionId(), token, taskId, text, claimed: false, at: Date.now(),
    photo: files && await files.photo.arrayBuffer(), thumb: files && await files.thumb.arrayBuffer(),
  })
  mirror()
  registerSync()
  await refresh()
  now()
  return true
}

// Called once when the app starts
export function resumeUploads() {
  mirror()
  now()
  window.addEventListener('online', now)
  document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && now())
  // The service worker sent something while the app was open: show it and fetch the new totals
  navigator.serviceWorker?.addEventListener('message', (e) => {
    if (e.data !== SYNC_TAG) return
    void refresh()
    sentListeners.forEach((l) => l())
  })
}

// ---------------------------------------------------------------- the photo

async function jpeg(bitmap: ImageBitmap, side: number, maxBytes: number): Promise<Blob> {
  const scale = Math.min(1, side / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  // A detailed photo can come out over the server's limit: a little less quality until it fits
  for (const quality of [0.85, 0.7, 0.55, 0.4]) {
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    if (!blob) break
    if (blob.size <= maxBytes) return blob
  }
  throw new Error('jpeg')
}

// Phone photos are 4000 px and several MB: redraw at most 1600 px on the long side as JPEG, which keeps no location
// or camera data, and a 400 px copy for the moderators' list
export async function prepare(file: Blob): Promise<{ photo: Blob; thumb: Blob }> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  try {
    return { photo: await jpeg(bitmap, MAX_SIDE, MAX_BYTES), thumb: await jpeg(bitmap, THUMB_SIDE, THUMB_MAX_BYTES) }
  } finally {
    bitmap.close()
  }
}
