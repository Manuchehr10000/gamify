import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { API_URL, api } from '../api'
import { BadgeIcons } from '../components/console/rewards'
import { Icon, Shell, Stripe } from '../components/console/ui'
import type { Hall as HallData, HallLogo, HallMode } from '../rating'

const POLL_MS = 10_000
const PUSH_MS = 15_000
// Pushes, and badges marked «на экран», interrupt the cycle and the logo slides; «Эфир» and «Пауза» are never
// interrupted
const PUSH_MODES: HallMode[] = ['auto', 'logos']
// A logo that hasn't loaded by then is left out of its slide
const PRELOAD_MS = 5000
// A logo held on screen (a pause) is logged in parts, so each entry stays within the server's 30 seconds
const LOG_CUT_MS = 20_000
const LOG_MAX_AGE_MS = 2 * 60 * 60 * 1000
const LOG_KEY = 'hall_logo_shows'
const LOG_BATCH = 200

type Slide = { kind: 'top' } | { kind: 'logos'; logos: HallLogo[] } | { kind: 'countdown' }
type Show = { partner_id: number; started_at: string; seconds: number }

// Logs made while offline wait in the screen's storage until the network returns
function readLog(): Show[] {
  try {
    return JSON.parse(localStorage.getItem(LOG_KEY) ?? '[]')
  } catch {
    return []
  }
}

function writeLog(shows: Show[]) {
  try {
    localStorage.setItem(LOG_KEY, JSON.stringify(shows))
  } catch {
    // Storage blocked: the shows stay in memory until sent
  }
}

// Resolves once the image is in the browser's cache, or false when it fails or takes too long
function preload(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image()
    const timer = setTimeout(() => resolve(false), PRELOAD_MS)
    img.onload = () => {
      clearTimeout(timer)
      resolve(true)
    }
    img.onerror = () => {
      clearTimeout(timer)
      resolve(false)
    }
    img.src = API_URL + url
  })
}

function onAir(hall: HallData, clock: number): boolean {
  return hall.mode === 'live' || (hall.mode === 'auto' && hall.live_from !== null && clock >= Date.parse(hall.live_from))
}

function remaining(ms: number): string {
  const s = Math.max(0, Math.ceil(ms / 1000))
  const mm = String(Math.floor(s / 60) % 60).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return s >= 3600 ? `${Math.floor(s / 3600)}:${mm}:${ss}` : `${mm}:${ss}`
}

// The hall's big screen: no login, read-only, the dark board in a woodgrain frame. In «Авто» it cycles the top 10,
// partner logos and a countdown; in the last minutes of the day it goes to «Эфир» by itself. A dropped network
// keeps cycling what it has, on its own clock, until it comes back
export function Hall() {
  const { t } = useTranslation()
  const [hall, setHall] = useState<HallData | null>(null)
  const [offline, setOffline] = useState(false)
  // The server's clock minus this screen's, so «Эфир» and the countdown follow the server
  const [skew, setSkew] = useState(0)
  const [clock, setClock] = useState(() => Date.now())
  const [slide, setSlide] = useState<Slide>({ kind: 'top' })
  const [push, setPush] = useState<string | null>(null)
  // What «Пауза» holds: «Эфир» if it was on when the pause came
  const [pausedOnAir, setPausedOnAir] = useState(false)

  const hallRef = useRef<HallData | null>(null)
  const skewRef = useRef(0)
  const pushRef = useRef(false)
  const pushTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const seenPushes = useRef(new Set<number>())
  const seenBadges = useRef(new Set<number>())
  const step = useRef(0)
  const logoSlides = useRef(0)
  const loaded = useRef(new Set<string>())
  const [stored] = useState(readLog)
  const log = useRef<Show[]>(stored)
  const sending = useRef(false)
  // The logos on screen now and since when
  const showing = useRef<{ ids: number[]; since: number } | null>(null)
  // Starts the cycle's next slide now: set by the cycle, called when the mode changes
  const kick = useRef<() => void>(() => {})

  const serverNow = useCallback(() => Date.now() + skewRef.current, [])

  const record = useCallback((ids: number[], since: number, until: number) => {
    const seconds = Math.round((until - since) / 1000)
    if (seconds < 1) return
    const started = new Date(since).toISOString()
    log.current = [...log.current, ...ids.map((id) => ({ partner_id: id, started_at: started, seconds: Math.min(seconds, 30) }))]
    writeLog(log.current)
  }, [])

  const flush = useCallback(() => {
    const cutoff = serverNow() - LOG_MAX_AGE_MS
    log.current = log.current.filter((s) => Date.parse(s.started_at) >= cutoff)
    if (sending.current || log.current.length === 0) return
    const batch = log.current.slice(0, LOG_BATCH)
    sending.current = true
    api('/api/hall/logo-shows', { json: { shows: batch }, timeoutMs: 8000 })
      .then(() => {
        log.current = log.current.filter((s) => !batch.includes(s))
        writeLog(log.current)
      })
      // Kept for the next poll
      .catch(() => {})
      .finally(() => {
        sending.current = false
      })
  }, [serverNow])

  // Poll every 10 seconds: the ranking, the mode and the slides' content; send the logo log; cut a held logo's entry
  useEffect(() => {
    let alive = true
    const load = () => {
      const open = showing.current
      if (open && serverNow() - open.since >= LOG_CUT_MS) {
        const now = serverNow()
        record(open.ids, open.since, now)
        showing.current = { ids: open.ids, since: now }
      }
      flush()
      api<HallData>('/api/hall', { timeoutMs: 8000 })
        .then((data) => {
          if (!alive) return
          const before = hallRef.current
          const offset = Date.parse(data.now) - Date.now()
          if (data.mode === 'pause' && before?.mode !== 'pause') {
            // A screen that opens already paused holds what «Авто» would show now
            setPausedOnAir(onAir(before ?? { ...data, mode: 'auto' }, Date.now() + (before ? skewRef.current : offset)))
          }
          if (data.push && !seenPushes.current.has(data.push.id)) {
            seenPushes.current.add(data.push.id)
            if (PUSH_MODES.includes(data.mode) && !onAir(data, Date.now() + offset)) {
              pushRef.current = true
              setPush(data.push.text)
              pushTimer.current = setTimeout(() => {
                pushRef.current = false
                setPush(null)
              }, PUSH_MS)
            }
          }
          // A badge shows the same way, after any push: the server sends one at a time and none while a push shows
          if (data.badge && !pushRef.current && !seenBadges.current.has(data.badge.id)) {
            seenBadges.current.add(data.badge.id)
            if (PUSH_MODES.includes(data.mode) && !onAir(data, Date.now() + offset)) {
              pushRef.current = true
              setPush(t('hall.badge', { name: data.badge.name, badge: data.badge.badge }))
              pushTimer.current = setTimeout(() => {
                pushRef.current = false
                setPush(null)
              }, PUSH_MS)
            }
          }
          hallRef.current = data
          skewRef.current = offset
          setSkew(offset)
          setHall(data)
          setOffline(false)
          if (before !== null && before.mode !== data.mode && (data.mode === 'auto' || data.mode === 'logos')) kick.current()
        })
        .catch(() => alive && setOffline(true))
    }
    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
      clearTimeout(pushTimer.current)
    }
  }, [flush, record, serverNow, t])

  // The countdown and «Эфир» run on the screen's own clock between polls
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  // The cycle: the next slide every «slide time» seconds, its logos loaded before it shows. A switch of mode starts
  // the next slide at once, so «Только логотипы» and «Авто» reach the screen with the poll that brought them
  useEffect(() => {
    let alive = true
    let run = 0
    let timer: ReturnType<typeof setTimeout>
    const schedule = () => {
      clearTimeout(timer)
      timer = setTimeout(next, (hallRef.current?.slide_seconds ?? 8) * 1000)
    }
    // A run that a newer one overtook (a switch while logos loaded) shows nothing and schedules nothing
    const stale = (mine: number) => !alive || mine !== run
    const next = async () => {
      const mine = ++run
      const h = hallRef.current
      const now = Date.now() + skewRef.current
      const holding = !h || pushRef.current || h.mode === 'pause' || onAir(h, now)
      if (h && !holding) {
        const order: Slide['kind'][] = h.mode === 'logos' ? ['logos'] : ['top', 'logos', 'countdown']
        let shown = false
        // A slide with nothing to show is skipped; a logo slide whose partners all wait for a later turn too
        for (let tries = 0; tries < order.length + 10 && !shown; tries++) {
          step.current = (step.current + 1) % order.length
          const kind = order[step.current]
          if (kind === 'top') {
            setSlide({ kind })
            shown = true
          } else if (kind === 'countdown') {
            if (h.next && Date.parse(h.next.at) > now) {
              setSlide({ kind })
              shown = true
            }
          } else {
            const n = logoSlides.current++
            const due = h.logos.filter((lg) => n % lg.every === 0)
            const ok = await Promise.all(due.map((lg) => preload(lg.url).then((good) => {
              if (good) loaded.current.add(lg.url)
              // Already loaded once: the browser's cache still has it while offline
              return good || loaded.current.has(lg.url)
            })))
            if (stale(mine)) return
            const logos = due.filter((_, i) => ok[i])
            // A switch that came while the logos loaded wins: «Пауза» holds what was on screen
            const after = hallRef.current
            if (!after || pushRef.current || after.mode === 'pause' || onAir(after, Date.now() + skewRef.current)) break
            if (logos.length > 0) {
              setSlide({ kind, logos })
              shown = true
            }
          }
        }
        // «Только логотипы» with no logo to show: the board with the partners' title only, never the top 10
        if (!shown && hallRef.current?.mode === 'logos') setSlide((s) => (s.kind === 'logos' ? s : { kind: 'logos', logos: [] }))
      }
      if (!stale(mine)) schedule()
    }
    kick.current = () => {
      clearTimeout(timer)
      void next()
    }
    schedule()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])

  const now = clock + skew
  const air = hall !== null && (onAir(hall, now) || (hall.mode === 'pause' && pausedOnAir))
  const view = air ? 'air' : push !== null ? 'push' : slide.kind
  const visibleLogos = view === 'logos' && slide.kind === 'logos' ? slide.logos : null
  const visibleKey = visibleLogos?.map((lg) => lg.id).join(',') ?? ''

  // Each time logos show, log the partners, when and for how long
  useEffect(() => {
    const ids = visibleKey ? visibleKey.split(',').map(Number) : []
    if (ids.length > 0) showing.current = { ids, since: serverNow() }
    return () => {
      const open = showing.current
      if (open) record(open.ids, open.since, serverNow())
      showing.current = null
    }
  }, [visibleKey, slide, record, serverNow])

  const style = { '--hall-min-font': `${hall?.min_font_px ?? 40}px` } as CSSProperties
  return (
    <Shell theme="dark" className="gc-hall-board gc-wood">
      <div className={`gc-hall-board__screen ${view === 'air' ? 'gc-hall-board__screen--air' : ''}`} style={style}>
        <header className="gc-hall-board__titles">
          <p className="gc-hall-board__event">{t('hall.forum')}</p>
          {view === 'air' && (
            <p className="gc-hall-board__on-air">
              <span className="gc-hall-board__on-air-dot" aria-hidden />
              {t('hall.onAir')}
            </p>
          )}
        </header>
        <Stripe className="gc-hall-board__stripe" />
        {offline && (
          <p className="gc-hall-board__notice gc-hall-board__notice--offline" role="status">
            <Icon name="wifi-off" size={32} />
            <span>{t('hall.offline')}</span>
          </p>
        )}
        <div key={view === 'logos' ? `logos-${visibleKey}` : view} className="gc-hall-board__slide">
          {(view === 'air' || view === 'top') && <Top hall={hall} />}
          {view === 'push' && <p className="gc-hall-board__push">{push}</p>}
          {view === 'countdown' && hall?.next && (
            <div className="gc-hall-board__countdown">
              <p className="gc-hall-board__countdown-what">{t(`hall.countdown.${hall.next.kind}`)}</p>
              {hall.next.name && <p className="gc-hall-board__countdown-name">{hall.next.name}</p>}
              <p className="gc-hall-board__countdown-left gc-num">{remaining(Date.parse(hall.next.at) - now)}</p>
            </div>
          )}
          {view === 'countdown' && !hall?.next && <Top hall={hall} />}
          {visibleLogos && (
            <div className="gc-hall-board__logos">
              <p className="gc-hall-board__logos-title">{t('hall.partners')}</p>
              <ul className="gc-hall-board__logo-grid">
                {visibleLogos.map((lg) => (
                  <li key={lg.id} className={`gc-hall-board__logo gc-hall-board__logo--${lg.size}`}>
                    <img src={API_URL + lg.url} alt={lg.name} onError={(e) => { e.currentTarget.parentElement!.hidden = true }} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Shell>
  )
}

// The top 10 in huge type, as 007: the frozen places with «Итоги зафиксированы» once the admin froze them
function Top({ hall }: { hall: HallData | null }) {
  const { t } = useTranslation()
  return (
    <>
      <h1 className="gc-hall-board__title gc-display-xl">{t('hall.title')}</h1>
      {hall?.frozen && (
        <p className="gc-hall-board__notice gc-hall-board__notice--frozen" role="status">
          <Icon name="lock" size={40} />
          <span>{t('hall.frozen')}</span>
        </p>
      )}
      {hall && hall.top.length === 0 && <p className="gc-hall-board__empty">{t('hall.empty')}</p>}
      {hall && hall.top.length > 0 && (
        <ol className="gc-hall-board__list">
          {hall.top.map((r) => (
            <li key={r.place} className={`gc-hall-board__row ${r.place <= 3 ? 'gc-hall-board__row--top' : ''}`}>
              <span className="gc-hall-board__place gc-score-l gc-num">{r.place}</span>
              <span className="gc-hall-board__who">
                <span className="gc-hall-board__name">{r.name}</span>
                {r.badges.length > 0 && <span className="gc-hall-board__badges"><BadgeIcons badges={r.badges} /></span>}
                {r.level && <span className="gc-hall-board__level">{r.level}</span>}
              </span>
              <span className={`gc-hall-board__points ${r.place <= 3 ? 'gc-score-xl' : 'gc-score-l'} gc-num`}>{r.points}</span>
            </li>
          ))}
        </ol>
      )}
    </>
  )
}
