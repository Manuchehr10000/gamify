import { useSyncExternalStore } from 'react'
import { api, ApiError, tokens } from './api'
import { cache, type Award } from './feed'

// Photos and texts on their way to the server. Kept in memory while the app is open:
// closing the app loses what was not sent yet.
export type Upload =
  | { state: 'sending' }
  | { state: 'offline' }
  | { state: 'failed'; reason: string }
  | { state: 'sent'; award: Award }

// A slow cell can take a while for a 1600 px photo; past this the upload is retried with twice the time
const TIMEOUT_FIRST_MS = 60_000
const TIMEOUT_MAX_MS = 8 * 60_000
const RETRY_FIRST_MS = 3_000
const RETRY_MAX_MS = 30_000
// The phone shrinks photos to this before sending; the server refuses bigger ones
const MAX_SIDE = 1600

const uploads = new Map<number, Upload>()
const listeners = new Set<() => void>()
const sentListeners = new Set<() => void>()

function set(taskId: number, upload: Upload | null) {
  if (upload) uploads.set(taskId, upload)
  else uploads.delete(taskId)
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// Called whenever an upload goes through, so the feed can fetch the new totals
export function onSent(listener: () => void) {
  sentListeners.add(listener)
  return () => {
    sentListeners.delete(listener)
  }
}

export function useUpload(taskId: number): Upload | null {
  return useSyncExternalStore(subscribe, () => uploads.get(taskId) ?? null)
}

// Forget a finished upload once its result was shown; the server's task says «Выполнено» from then on
export function forgetUpload(taskId: number) {
  const u = uploads.get(taskId)
  if (u && (u.state === 'sent' || u.state === 'failed')) set(taskId, null)
}

// Wait until the network is back or the delay has passed, whichever comes first
function pause(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer)
      window.removeEventListener('online', done)
      resolve()
    }
    const timer = setTimeout(done, ms)
    window.addEventListener('online', done)
  })
}

// No real answer from the server: the proxy, a restart or overload, not a refusal of what was sent
const retryable = (err: ApiError) => err.status >= 500 || err.status === 408 || err.status === 429

async function run(taskId: number, send: (timeoutMs: number) => Promise<Award>) {
  let delay = RETRY_FIRST_MS
  let timeout = TIMEOUT_FIRST_MS
  for (;;) {
    set(taskId, { state: 'sending' })
    try {
      const award = await send(timeout)
      // The feed's copy on the phone shows «Выполнено» at once, even if the next feed load fails
      const feed = cache.feed()
      if (feed && award.result !== 'unavailable') {
        cache.saveFeed({ ...feed, tasks: feed.tasks.map((t) => (t.id === taskId ? award.task : t)) })
      }
      set(taskId, { state: 'sent', award })
      sentListeners.forEach((l) => l())
      return
    } catch (err) {
      // The server answered with a refusal: sending the same thing again won't change it
      if (err instanceof ApiError && !retryable(err)) {
        set(taskId, { state: 'failed', reason: typeof err.detail === 'string' ? err.detail : '' })
        return
      }
      // No answer (offline, dropped, timed out, server hiccup): try again. A retry of an upload the server did get
      // comes back as «already», so the points are counted once.
      set(taskId, { state: 'offline' })
      await pause(delay)
      delay = Math.min(delay * 2, RETRY_MAX_MS)
      timeout = Math.min(timeout * 2, TIMEOUT_MAX_MS)
    }
  }
}

function start(taskId: number, send: (timeoutMs: number) => Promise<Award>) {
  const u = uploads.get(taskId)
  if (u && (u.state === 'sending' || u.state === 'offline')) return
  void run(taskId, send)
}

// One key per send, repeated on its retries: the server tells a late retry of a photo a moderator sent back
// from the guest sending the same photo or text again
// (crypto.randomUUID needs https, and a phone on the venue's network may open the app over plain http)
const uploadKey = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

export function sendPhoto(taskId: number, photo: Blob, text?: string) {
  const upload = uploadKey()
  start(taskId, (timeoutMs) => {
    // A FormData can't be sent twice on every browser: build it for each attempt
    const form = new FormData()
    form.append('photo', photo, 'photo.jpg')
    if (text !== undefined) form.append('text', text)
    form.append('upload', upload)
    return api<Award>(`/api/tasks/${taskId}/photo`, { token: tokens.get('guest'), form, timeoutMs })
  })
}

export function sendText(taskId: number, text: string) {
  const upload = uploadKey()
  start(taskId, (timeoutMs) =>
    api<Award>(`/api/tasks/${taskId}/text`, { token: tokens.get('guest'), json: { text, upload }, timeoutMs }),
  )
}

// Phone photos are 4000 px and several MB: redraw at most 1600 px on the long side as JPEG
export async function shrink(file: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('jpeg'))), 'image/jpeg', 0.85),
  )
}
