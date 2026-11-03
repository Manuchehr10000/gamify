import { useEffect } from 'react'
import { api, tokens } from './api'

// A push as the feed sends it: the latest one still inside its 10-minute life
export type FeedPush = {
  id: number
  // A stage push is the stage banner the feed already shows, so it isn't shown twice
  kind: 'stage' | 'market' | 'quiz_before' | 'quiz_open' | 'one_off'
  title: string
  text: string
  url: string
}

// Storage can be blocked (private mode): then the phone may be asked again, and the guide shows again
function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // not kept
  }
}

const ASKED_KEY = 'push_asked'
const GUIDE_KEY = 'push_guide_closed'
const SEEN_KEY = 'push_seen'

// An iPhone or iPad (iPadOS says it is a Mac, but has a touch screen)
const ios = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

const standalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true

// iPhone Safari can't take pushes: the app must be added to the Home Screen first, and the guide says how
export const needsHomeScreen = () => ios() && !standalone()

const canPush = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

// The app asks once per phone: never after «Не сейчас» or the browser's «Block», never in iPhone Safari
export const mayAsk = () =>
  canPush() && !needsHomeScreen() && Notification.permission !== 'denied' && read(ASKED_KEY) === null

export const markAsked = () => write(ASKED_KEY, '1')

export const guideClosed = () => read(GUIDE_KEY) === '1'
export const closeGuide = () => write(GUIDE_KEY, '1')

// While the guide shows, the address carries the login the badge link gave, in the same #token fragment, so the Home
// Screen app (which has its own storage) opens signed in on this same page. Only the fragment changes, so Back and the
// router's own entries are untouched; it goes again when the guide closes
export function useLoginInAddress(on: boolean) {
  useEffect(() => {
    const token = tokens.get('guest')
    if (!on || !token) return
    const path = window.location.pathname + window.location.search
    window.history.replaceState(window.history.state, '', `${path}#token=${token}`)
    return () => {
      if (window.location.pathname + window.location.search === path) window.history.replaceState(window.history.state, '', path)
    }
  }, [on])
}

// The Home Screen app opens on the page it was added from with #token: the login is kept and the address cleaned.
// /app/welcome reads its own (the badge link's)
export function takeLoginFromAddress() {
  const fresh = new URLSearchParams(window.location.hash.slice(1)).get('token')
  if (!fresh || !window.location.pathname.startsWith('/app') || window.location.pathname === '/app/welcome') return
  try {
    tokens.set('guest', fresh)
  } catch {
    return
  }
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
}

// Each push's banner shows once on this phone
export function firstSight(id: number): boolean {
  let seen: number[] = []
  try {
    seen = JSON.parse(read(SEEN_KEY) ?? '[]') as number[]
  } catch {
    // start afresh
  }
  if (seen.includes(id)) return false
  write(SEEN_KEY, JSON.stringify([...seen, id].slice(-20)))
  return true
}

function serverKey(base64: string): Uint8Array<ArrayBuffer> {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
}

// The browser's own prompt first, while the tap still counts (Safari and Firefox refuse a prompt after an await), then
// the subscription sent to the server. The key comes from /api/me, read before the tap. false when the guest said no
export async function enablePush(token: string, key: string): Promise<boolean> {
  markAsked()
  const permission = Notification.requestPermission()
  if ((await permission) !== 'granted' || !key) return false
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: serverKey(key) })
  await api('/api/push/subscribe', { token, json: subscription.toJSON() })
  return true
}
