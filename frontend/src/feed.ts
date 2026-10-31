export type Stage = { number: number; name: string; starts_at: string; ends_at: string; message: string }
export type Task = {
  id: number
  type: string
  text: string
  points: number
  coins: number
  partner_name: string
  window_end: string | null
  done: boolean
}
export type Feed = {
  state: 'none' | 'before' | 'running' | 'over'
  stage_count: number
  starts_at: string | null
  stage: Stage | null
  tasks: Task[]
}

// Forum times are Dushanbe times, whatever zone the phone is set to
const clock = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Dushanbe' })
export const hhmm = (iso: string) => clock.format(new Date(iso))

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
    try {
      return JSON.parse(raw) as Feed
    } catch {
      return null
    }
  },
  saveFeed: (feed: Feed) => write(FEED_KEY, JSON.stringify(feed)),
  task: (id: number): Task | null => cache.feed()?.tasks.find((t) => t.id === id) ?? null,
  // The stage number this phone last showed, to tell when it changed
  lastStage: (): number | null => {
    const raw = read(STAGE_KEY)
    return raw ? Number(raw) : null
  },
  saveStage: (n: number) => write(STAGE_KEY, String(n)),
}
