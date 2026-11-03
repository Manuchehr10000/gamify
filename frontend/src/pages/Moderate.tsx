import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, api, blob, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { StatTile } from '../components/console/staff'
import { Amount, Button, Callout, Checkbox, Loading, MessageCard, Screen, Spinner, Stripe } from '../components/console/ui'
import { hhmm } from '../feed'

type Item = { id: number; task: string; points: number; guest: string; text: string; photo: boolean; created_at: string }
type Queue = { moderator: string; waiting: number; oldest_seconds: number | null; items: Item[] }
type Action = 'accept' | 'bonus' | 'retake' | 'penalty'
type Decision = { result: 'decided' | 'already'; status: string; moderator: string; decided_at: string | null }

// A guest's photo shows up within 10 seconds
const POLL_MS = 5_000

// The moderator's tablet: unchecked photos and texts, newest first, each decided once
export function Moderate() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('moderator'))
  const [queue, setQueue] = useState<Queue | null>(null)
  const [top20, setTop20] = useState(false)
  const [error, setError] = useState(false)
  // Decided here: kept off the list even if a poll that started before the decision brings them back
  const [decided, setDecided] = useState<ReadonlySet<number>>(new Set())
  // Only the latest request may fill the list: an answer for the old filter can arrive after «Топ-20» is switched
  const latest = useRef(0)

  const logOut = useCallback(() => {
    tokens.clear('moderator')
    setToken(null)
  }, [])

  const load = useCallback(async () => {
    if (!token) return
    const mine = ++latest.current
    try {
      const q = await api<Queue>(`/api/moderation/queue${top20 ? '?top20=true' : ''}`, { token })
      if (mine !== latest.current) return
      setQueue(q)
      setError(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) logOut()
      else if (mine === latest.current) setError(true)
    }
  }, [token, top20, logOut])

  useEffect(() => {
    // The first load and the timer both refresh the queue from outside React's render
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
    const timer = setInterval(load, POLL_MS)
    const wake = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', wake)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [load])

  if (!token) return <StaffLogin role="moderator" onLogin={setToken} />

  const items = queue?.items.filter((i) => !decided.has(i.id)) ?? []
  const oldest = queue?.oldest_seconds ?? null
  return (
    <Screen theme="label" wide>
      <header className="gc-moderate-head">
        <h1 className="gc-moderate-head__name gc-display-m">{queue?.moderator ?? t('staff.moderatorTitle')}</h1>
        <Checkbox checked={top20} onChange={setTop20}>{t('moderate.top20')}</Checkbox>
        <Stripe className="gc-moderate-head__stripe" />
      </header>
      {queue && (
        <div className="gc-moderate-stats">
          <StatTile label={t('live.waiting')} value={queue.waiting} />
          {oldest !== null && (
            <StatTile
              label={t('live.oldest')}
              value={oldest < 60 ? t('moderate.oldestNow') : t('live.minutes', { count: Math.floor(oldest / 60) })}
            />
          )}
        </div>
      )}
      {error && <Callout tone="danger">{t('common.error')}</Callout>}
      {!queue && !error && <Loading />}
      {queue && items.length === 0 && <MessageCard icon="check" title={t('moderate.empty')} />}
      {items.length > 0 && (
        <ul className="gc-moderation-grid">
          {items.map((item) => (
            <li key={item.id}>
              <ItemCard
                item={item}
                token={token}
                onDecided={() => {
                  setDecided((d) => new Set(d).add(item.id))
                  setQueue((q) => (q ? { ...q, waiting: Math.max(0, q.waiting - 1) } : q))
                }}
                onLoggedOut={logOut}
              />
            </li>
          ))}
        </ul>
      )}
    </Screen>
  )
}

function ItemCard({ item, token, onDecided, onLoggedOut }:
  { item: Item; token: string; onDecided: () => void; onLoggedOut: () => void }) {
  const { t } = useTranslation()
  const photo = usePhoto(item.photo ? item.id : null, token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [already, setAlready] = useState('')

  async function decide(action: Action) {
    setBusy(true)
    setError('')
    try {
      const r = await api<Decision>(`/api/submissions/${item.id}/decision`, { token, json: { action } })
      // Someone else was first: say who, and let the next poll take it off the list
      if (r.result === 'already') setAlready(r.moderator)
      else onDecided()
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onLoggedOut()
      else if (err instanceof ApiError && typeof err.detail === 'string') {
        setError(t(`moderate.errors.${err.detail}`, { defaultValue: t('common.error') }))
      } else setError(t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="gc-moderation-card" aria-busy={busy || undefined} aria-label={`${item.guest} · ${item.task}`}>
      {item.photo && (
        <div className="gc-photo-frame gc-crt" aria-busy={!photo || undefined}>
          {photo
            ? <img src={photo} alt={t('moderate.photoAlt')} className="gc-photo-frame__img" />
            : <Spinner size={32} label={t('common.loading')} />}
        </div>
      )}
      {item.text && <p className="gc-moderation-card__text gc-body">{item.text}</p>}
      <p className="gc-moderation-card__task gc-label">{item.task}</p>
      <p className="gc-moderation-card__meta gc-body-s">
        <span className="gc-moderation-card__guest">{item.guest}</span>
        <Amount kind="points" count={item.points} size="s" />
        <span>{t('moderate.sentAt', { time: hhmm(item.created_at) })}</span>
      </p>
      {already ? (
        <Callout tone="info" icon="eye">{t('moderate.already', { name: already })}</Callout>
      ) : (
        <div className="gc-moderation-card__actions">
          <Button disabled={busy} onClick={() => decide('accept')}>{t('moderate.accept')}</Button>
          <Button variant="outline" disabled={busy} onClick={() => decide('bonus')}>{t('moderate.bonus')}</Button>
          <Button variant="outline" disabled={busy} onClick={() => decide('retake')}>{t('moderate.retake')}</Button>
          <Button variant="danger" disabled={busy} onClick={() => decide('penalty')}>{t('moderate.penalty')}</Button>
        </div>
      )}
      {error && <Callout tone="danger">{error}</Callout>}
    </article>
  )
}

// Try a photo that didn't load again after this long, so a dropped connection doesn't leave the card blank
const PHOTO_RETRY_MS = 3_000

// An <img> can't send the moderator's token: fetch the photo, show it from memory, let it go when the card leaves
function usePhoto(id: number | null, token: string): string {
  const [url, setUrl] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (id === null) return
    let objectUrl = ''
    let gone = false
    let retry: ReturnType<typeof setTimeout> | undefined
    blob(`/api/submissions/${id}/photo`, { token })
      .then((photo) => {
        if (gone) return
        objectUrl = URL.createObjectURL(photo)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!gone) retry = setTimeout(() => setAttempt((a) => a + 1), PHOTO_RETRY_MS)
      })
    return () => {
      gone = true
      clearTimeout(retry)
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [id, token, attempt])
  return url
}
