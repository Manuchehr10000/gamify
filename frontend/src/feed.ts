import type { Badge } from './badges'
import type { FeedPush } from './push'

// multiplier: the stage's points multiplier (1 to 5 in steps of 0.5); a feed saved before it came has none
export type Stage = { number: number; name: string; starts_at: string; ends_at: string; message: string; multiplier?: number }
export type Task = {
  id: number
  type: string
  text: string
  points: number
  coins: number
  partner_name: string
  window_end: string | null
  done: boolean
  // The card's label: «Доступно» · «На проверке» (sent, not yet decided; already paid) · «Выполнено» ·
  // «Временно недоступно» (all its places are taken)
  state: 'available' | 'review' | 'done' | 'full'
  method: 'qr' | 'link' | 'market' | 'photo' | 'text' | 'photo_text' | 'quiz' | ''
  link: string
  // A quiz's countdown in seconds; null without one
  timer_seconds: number | null
  // A quiz whose hall QR («Требует») the guest hasn't scanned yet
  locked: boolean
  // A moderator's word: retake (send again) · penalty (rejected, task closed) · ''
  review: '' | 'retake' | 'penalty'
}
export type Feed = {
  points: number
  coins: number
  // The level the points reach; '' with no levels loaded
  level: string
  // Points still needed for the next level; null at the top
  to_next: number | null
  // Set once, right after the guest climbed past the level they last saw: the full-screen moment
  new_level: string | null
  // Badges just earned, sent once each: a full-screen moment each, after the level's
  new_badges: Badge[]
  // How many photos and texts this phone may keep waiting to send (the admin's setting)
  queue_size: number
  // The latest push still inside its 10-minute life: its banner shows once; a feed saved before pushes has none
  push?: FeedPush | null
  // Task points earned: the app may ask, once per phone
  ask_push?: boolean
  state: 'none' | 'before' | 'running' | 'over'
  stage_count: number
  starts_at: string | null
  stage: Stage | null
  tasks: Task[]
}

export type Award = { result: 'awarded' | 'already' | 'unavailable' | 'limit'; task: Task }

// The batch of cards moves on only on a page load of /app (opening the app or a reload): the document's first path,
// and only once per load. Polls, coming back to the screen and returning from a task keep the batch
const loadedAtFeed = window.location.pathname.replace(/\/$/, '') === '/app'
let advanced = false

export function feedPath(): { path: string; method: 'GET' | 'POST' } {
  if (!loadedAtFeed || advanced) return { path: '/api/feed', method: 'GET' }
  advanced = true
  return { path: '/api/feed/next', method: 'POST' }
}

// Forum times are Dushanbe times, whatever zone the phone is set to
const clock = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Dushanbe' })
export const hhmm = (iso: string) => clock.format(new Date(iso))

// «×2», «×1,5» (Russian decimal comma) when the stage multiplies points; null at ×1
export function multiplierMark(stage: Stage): string | null {
  const m = stage.multiplier ?? 1
  return m === 1 ? null : `×${m.toLocaleString('ru-RU')}`
}

// The last feed stays on the phone so a dropped network still shows something.
// Storage can be blocked (private mode): then there is simply no copy.
const FEED_KEY = 'last_feed'
const STAGE_KEY = 'last_stage'

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
    // no copy kept
  }
}

export const cache = {
  feed: (): Feed | null => {
    const raw = read(FEED_KEY)
    if (!raw) return null
    let feed: Feed
    try {
      feed = JSON.parse(raw) as Feed
    } catch {
      return null
    }
    // The saved cards are the stage's: once it has ended, an undecided «На проверке» shows «Выполнено»,
    // worked out from the stage as the server does
    const ended = feed.stage && Date.now() >= new Date(feed.stage.ends_at).getTime()
    return ended ? { ...feed, tasks: feed.tasks.map((t) => (t.state === 'review' ? { ...t, state: 'done' } : t)) } : feed
  },
  saveFeed: (feed: Feed) => write(FEED_KEY, JSON.stringify(feed)),
  task: (id: number): Task | null => cache.feed()?.tasks.find((t) => t.id === id) ?? null,
  // The stage number this phone last showed, to tell when it changed
  lastStage: (): number | null => {
    const raw = read(STAGE_KEY)
    return raw ? Number(raw) : null
  },
  saveStage: (n: number) => write(STAGE_KEY, String(n)),
  // A link task's confirm tick shows only once its link was opened on this phone
  linkOpened: (id: number) => read(`link_opened_${id}`) === '1',
  markLinkOpened: (id: number) => write(`link_opened_${id}`, '1'),
}
