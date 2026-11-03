import { ChevronLeft, Coins } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { BADGE_ICONS, BADGES, type Badge } from '../badges'
import { Card, Screen } from '../components/ui'
import { useConfigVersion } from '../version'

type Entry = {
  // task (done, with what it earned) · buy (a market purchase) · arrival (points for coming)
  kind: 'task' | 'buy' | 'arrival'
  text: string
  points: number
  coins: number
  // A moderator's bonus; 0 without one
  bonus: number
  // A moderator rejected it and took its points and coins back
  rejected: boolean
  at: string
}
type ProfileData = {
  level: string
  to_next: number | null
  points: number
  // Below zero when a rejection took back coins already spent
  coins: number
  // The badges held now; the page shows all five and greys out the rest
  badges: Badge[]
  history: Entry[]
}

type State = { kind: 'loading' } | { kind: 'loggedOut' } | { kind: 'error' } | { kind: 'ready'; profile: ProfileData }

export function Profile() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))

  const load = useCallback(() => {
    const token = tokens.get('guest')
    if (!token) return
    api<ProfileData>('/api/profile', { token })
      .then((profile) => setState({ kind: 'ready', profile }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          tokens.clear('guest')
          setState({ kind: 'loggedOut' })
        } else {
          setState((s) => (s.kind === 'ready' ? s : { kind: 'error' }))
        }
      })
  }, [])

  useEffect(load, [load])
  // An admin's change (the levels) shows within 10 seconds
  useConfigVersion(load)

  if (state.kind === 'loading') return <Screen><p className="text-center text-slate-500">{t('common.loading')}</p></Screen>
  if (state.kind !== 'ready') {
    return (
      <Screen>
        <Card className="text-center text-lg font-medium">
          {t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')}
        </Card>
      </Screen>
    )
  }

  const { profile } = state
  return (
    <Screen>
      <div className="flex items-center gap-2">
        <Link to="/app" aria-label={t('feed.toFeed')} className="-ml-2 p-2"><ChevronLeft className="size-6" aria-hidden /></Link>
        <h1 className="text-xl font-semibold">{t('profile.title')}</h1>
      </div>
      <Card className="flex flex-col items-center gap-2 text-center">
        {profile.level && <p className="text-2xl font-bold">{profile.level}</p>}
        {profile.to_next !== null && <p className="text-sm text-slate-500">{t('feed.toNext', { count: profile.to_next })}</p>}
        <p className="mt-2 flex items-center gap-6 text-lg font-semibold">
          <span className="text-emerald-700">{t('feed.points', { count: profile.points })}</span>
          <span className={`flex items-center gap-1.5 ${profile.coins < 0 ? 'text-red-700' : 'text-amber-700'}`}>
            <Coins className="size-5" aria-hidden />
            {t('feed.coins', { count: profile.coins })}
          </span>
        </p>
      </Card>
      <h2 className="font-semibold">{t('badges.title')}</h2>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {BADGES.map((b) => {
          const Icon = BADGE_ICONS[b]
          const held = profile.badges.includes(b)
          return (
            <li
              key={b}
              className={`flex items-center gap-3 rounded-2xl px-4 py-3 ring-1 ${held ? 'bg-amber-50 ring-amber-200' : 'bg-slate-50 ring-slate-200'}`}
            >
              <span
                className={`flex size-10 shrink-0 items-center justify-center rounded-full ${held ? 'bg-amber-300 text-emerald-900' : 'bg-slate-200 text-slate-400'}`}
              >
                <Icon className="size-5" aria-hidden />
              </span>
              <span className="flex min-w-0 flex-col">
                <span className={`font-medium ${held ? 'text-slate-900' : 'text-slate-500'}`}>{t(`badges.${b}.name`)}</span>
                {!held && <span className="text-sm text-slate-500">{t(`badges.${b}.condition`)}</span>}
              </span>
            </li>
          )
        })}
      </ul>
      <h2 className="font-semibold">{t('profile.history')}</h2>
      {profile.history.length === 0 ? (
        <p className="py-8 text-center text-slate-500">{t('profile.empty')}</p>
      ) : (
        <ul className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
          {profile.history.map((e, i) => (
            <li key={i} className="flex flex-col gap-1 border-b border-slate-100 px-4 py-3 last:border-0">
              <p className={e.rejected ? 'text-slate-500 line-through' : ''}>
                {e.kind === 'arrival' ? t('profile.arrival') : e.text}
              </p>
              <EntryLine entry={e} />
            </li>
          ))}
        </ul>
      )}
    </Screen>
  )
}

function EntryLine({ entry: e }: { entry: Entry }) {
  const { t } = useTranslation()
  if (e.kind === 'buy') {
    return (
      <p className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-slate-500">{t('profile.spent')}</span>
        <span className="flex items-center gap-1 font-medium text-amber-700">
          <Coins className="size-4" aria-hidden />
          {t('feed.coins', { count: e.coins })}
        </span>
      </p>
    )
  }
  return (
    <p className="flex flex-wrap items-center gap-3 text-sm font-medium">
      <span className="text-emerald-700">{t('award.points', { count: e.points })}</span>
      {e.coins !== 0 && (
        <span className="flex items-center gap-1 text-amber-700">
          <Coins className="size-4" aria-hidden />
          {t('award.coins', { count: e.coins })}
        </span>
      )}
      {e.bonus > 0 && <span className="text-emerald-700">{t('profile.bonus', { count: e.bonus })}</span>}
      {e.rejected && <span className="text-red-700">{t('profile.rejected')}</span>}
    </p>
  )
}
