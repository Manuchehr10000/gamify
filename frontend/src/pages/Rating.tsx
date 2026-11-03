import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { LeaderboardRow } from '../components/console/rewards'
import { Callout, Loading, MessageCard, PageHeader, Screen } from '../components/console/ui'
import type { Rating as RatingData } from '../rating'
import { useConfigVersion } from '../version'

type State = { kind: 'loading' } | { kind: 'loggedOut' } | { kind: 'error' } | { kind: 'ready'; rating: RatingData }

export function Rating() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))

  const load = useCallback(() => {
    const token = tokens.get('guest')
    if (!token) return
    api<RatingData>('/api/rating', { token })
      .then((rating) => setState({ kind: 'ready', rating }))
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
  // An admin's change (the ranking size, a level) shows within 10 seconds
  useConfigVersion(load)

  if (state.kind === 'loading') return <Screen><Loading /></Screen>
  if (state.kind !== 'ready') {
    return (
      <Screen>
        <MessageCard icon="alert" title={t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')} />
      </Screen>
    )
  }

  const { rating } = state
  const inTop = rating.top.some((r) => r.me)
  return (
    <Screen>
      <PageHeader title={t('rating.title')} back={{ to: '/app', label: t('feed.toFeed') }} />
      {rating.frozen && <Callout tone="locked">{t('rating.frozen')}</Callout>}
      {rating.top.length === 0 ? (
        <MessageCard icon="trophy" title={t('rating.empty')} />
      ) : (
        <ol className="gc-list-group">
          {rating.top.map((r) => (
            <li key={r.place}><LeaderboardRow {...r} /></li>
          ))}
        </ol>
      )}
      {/* Outside the top: my place and points only (the API sends no name, level or badges for it) */}
      {!inTop && (
        <p className={`gc-my-place gc-body ${rating.me ? '' : 'gc-my-place--unranked'}`}>
          {rating.me
            ? t('rating.me', { place: rating.me.place, points: t('feed.points', { count: rating.me.points }) })
            : t('rating.notRanked')}
        </p>
      )}
    </Screen>
  )
}
