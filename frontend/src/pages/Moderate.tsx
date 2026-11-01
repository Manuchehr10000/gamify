import { Clock } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, api, blob, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card } from '../components/ui'
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
  return (
    <main className="min-h-dvh bg-slate-50 px-4 py-6 text-slate-900">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
        <header className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl bg-white px-5 py-3 shadow-sm ring-1 ring-slate-200">
          <span className="text-lg font-semibold">{queue?.moderator}</span>
          {queue && (
            <span className="flex flex-1 flex-wrap items-center gap-x-3 text-slate-700">
              <span className="font-medium">{t('moderate.waiting', { count: queue.waiting })}</span>
              {queue.oldest_seconds !== null && (
                <span className="flex items-center gap-1 text-slate-500">
                  <Clock className="size-4" aria-hidden />
                  {queue.oldest_seconds < 60
                    ? t('moderate.oldestNow')
                    : t('moderate.oldestMinutes', { count: Math.floor(queue.oldest_seconds / 60) })}
                </span>
              )}
            </span>
          )}
          <label className="flex items-center gap-2 font-medium">
            <input type="checkbox" className="size-5 accent-emerald-600" checked={top20} onChange={(e) => setTop20(e.target.checked)} />
            {t('moderate.top20')}
          </label>
        </header>
        {error && <p className="text-sm text-red-600">{t('common.error')}</p>}
        {!queue && !error && <p className="text-center text-slate-500">{t('common.loading')}</p>}
        {queue && items.length === 0 && <p className="py-12 text-center text-lg text-slate-500">{t('moderate.empty')}</p>}
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
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
      </div>
    </main>
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
    <Card className="flex flex-col gap-3 p-4">
      {item.photo && (
        <div className="flex h-72 items-center justify-center overflow-hidden rounded-xl bg-slate-100">
          {photo && <img src={photo} alt={t('moderate.photoAlt')} className="max-h-full max-w-full object-contain" />}
        </div>
      )}
      {item.text && <p className="whitespace-pre-line text-base">{item.text}</p>}
      <p className="text-sm font-medium text-slate-700">{item.task}</p>
      <div className="flex flex-wrap items-center gap-x-3 text-sm text-slate-500">
        <span className="font-medium text-slate-800">{item.guest}</span>
        <span className="text-emerald-700">{t('feed.points', { count: item.points })}</span>
        <span>{t('moderate.sentAt', { time: hhmm(item.created_at) })}</span>
      </div>
      {already ? (
        <p className="rounded-xl bg-slate-100 px-4 py-3 font-medium text-slate-700">{t('moderate.already', { name: already })}</p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Button disabled={busy} onClick={() => decide('accept')}>{t('moderate.accept')}</Button>
          <Button variant="outline" disabled={busy} onClick={() => decide('bonus')}>{t('moderate.bonus')}</Button>
          <Button variant="outline" disabled={busy} onClick={() => decide('retake')} className="h-auto min-h-12 py-2 text-sm">
            {t('moderate.retake')}
          </Button>
          <Button variant="danger" disabled={busy} onClick={() => decide('penalty')} className="h-auto min-h-12 py-2 text-sm">
            {t('moderate.penalty')}
          </Button>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </Card>
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
