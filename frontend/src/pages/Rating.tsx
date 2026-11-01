import { ChevronLeft, Lock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { Card, Screen } from '../components/ui'
import type { Rating as RatingData } from '../rating'

type State = { kind: 'loading' } | { kind: 'loggedOut' } | { kind: 'error' } | { kind: 'ready'; rating: RatingData }

export function Rating() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))

  useEffect(() => {
    const token = tokens.get('guest')
    if (!token) return
    api<RatingData>('/api/rating', { token })
      .then((rating) => setState({ kind: 'ready', rating }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          tokens.clear('guest')
          setState({ kind: 'loggedOut' })
        } else {
          setState({ kind: 'error' })
        }
      })
  }, [])

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

  const { rating } = state
  const inTop = rating.top.some((r) => r.me)
  return (
    <Screen>
      <div className="flex items-center gap-2">
        <Link to="/app" aria-label={t('feed.toFeed')} className="-ml-2 p-2"><ChevronLeft className="size-6" aria-hidden /></Link>
        <h1 className="text-xl font-semibold">{t('rating.title')}</h1>
      </div>
      {rating.frozen && (
        <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-800">
          <Lock className="size-4 shrink-0" aria-hidden />
          {t('rating.frozen')}
        </p>
      )}
      {rating.top.length === 0 ? (
        <p className="py-8 text-center text-slate-500">{t('rating.empty')}</p>
      ) : (
        <ol className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
          {rating.top.map((r) => (
            <li
              key={r.place}
              className={`flex items-center gap-3 border-b border-slate-100 px-4 py-3 last:border-0 ${r.me ? 'bg-emerald-50 font-semibold text-emerald-900' : ''}`}
            >
              <span className="w-8 text-right tabular-nums text-slate-500">{r.place}</span>
              <span className="flex-1 truncate">{r.name}</span>
              <span className="tabular-nums">{t('feed.points', { count: r.points })}</span>
            </li>
          ))}
        </ol>
      )}
      {!inTop && (
        <Card className="text-center font-medium">
          {rating.me
            ? t('rating.me', { place: rating.me.place, points: t('feed.points', { count: rating.me.points }) })
            : t('rating.notRanked')}
        </Card>
      )}
    </Screen>
  )
}
