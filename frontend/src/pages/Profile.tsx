import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import type { ShelfBadge } from '../badges'
import { DeletePhoto, HomeScreenGuide } from '../components/console/game'
import { BadgeTile, SectionHeading } from '../components/console/rewards'
import { Amount, Button, Card, Loading, MessageCard, PageHeader, Screen, StatusChip } from '../components/console/ui'
import { needsHomeScreen, useLoginInAddress } from '../push'
import { useConfigVersion } from '../version'

type Entry = {
  // task (done, with what it earned) · buy (a market purchase) · arrival (points for coming)
  kind: 'task' | 'buy' | 'arrival'
  text: string
  points: number
  coins: number
  // A moderator's bonus, or a blitz's speed bonus; 0 without one
  bonus: number
  // A moderator rejected it and took its points and coins back
  rejected: boolean
  // The guest deleted its photo before a decision: withdrawn, its points and coins taken back
  withdrawn: boolean
  // The task's photo the guest may delete, and whether it still waits for a moderator
  photo_id: number | null
  photo_undecided: boolean
  at: string
}
type ProfileData = {
  level: string
  to_next: number | null
  points: number
  // Below zero when a rejection took back coins already spent
  coins: number
  // Every badge switched on, in the order guests see them; the ones not held are greyed with their condition
  badges: ShelfBadge[]
  history: Entry[]
}

type State = { kind: 'loading' } | { kind: 'loggedOut' } | { kind: 'error' } | { kind: 'ready'; profile: ProfileData }

export function Profile() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))
  // The Home Screen guide closed in the feed opens again here (iPhone Safari only)
  const [guide, setGuide] = useState(false)
  useLoginInAddress(guide)

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

  if (state.kind === 'loading') return <Screen><Loading /></Screen>
  if (state.kind !== 'ready') {
    return (
      <Screen>
        <MessageCard icon="alert" title={t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')} />
      </Screen>
    )
  }

  const { profile } = state
  return (
    <Screen>
      <PageHeader title={t('profile.title')} back={{ to: '/app', label: t('feed.toFeed') }} />
      <Card className="gc-profile-head">
        {profile.level && <p className="gc-profile-head__level gc-display-m">{profile.level}</p>}
        {profile.to_next !== null && <p className="gc-profile-head__hint gc-body-s">{t('feed.toNext', { count: profile.to_next })}</p>}
        <p className="gc-profile-head__totals gc-crt">
          <Amount kind="points" count={profile.points} />
          <Amount kind="coins" count={profile.coins} alarm />
        </p>
      </Card>
      {needsHomeScreen() && (guide
        ? <HomeScreenGuide onClose={() => setGuide(false)} />
        : <Button variant="outline" icon="plus" onClick={() => setGuide(true)}>{t('profile.pushGuide')}</Button>)}
      <SectionHeading>{t('badges.title')}</SectionHeading>
      <ul className="gc-badge-grid">
        {profile.badges.map((b) => (
          <li key={b.code}><BadgeTile badge={b} /></li>
        ))}
      </ul>
      <SectionHeading>{t('profile.history')}</SectionHeading>
      {profile.history.length === 0 ? (
        <p className="gc-empty gc-body">{t('profile.empty')}</p>
      ) : (
        <ul className="gc-list-group">
          {profile.history.map((e, i) => (
            <li key={i}><HistoryRow entry={e} onDeleted={load} /></li>
          ))}
        </ul>
      )}
    </Screen>
  )
}

// What happened and what it earned or cost; a purchase reads «Покупка в маркете» and «−30 монет» (the API sends
// the coins spent below zero). No time: the history shows none
function HistoryRow({ entry: e, onDeleted }: { entry: Entry; onDeleted: () => void }) {
  const { t } = useTranslation()
  return (
    <div className={`gc-history-row ${e.rejected || e.withdrawn ? 'gc-history-row--rejected' : ''}`}>
      <p className="gc-history-row__title gc-body">{e.kind === 'arrival' ? t('profile.arrival') : e.text}</p>
      {e.kind === 'buy' ? (
        <p className="gc-history-row__line">
          <span className="gc-history-row__spent gc-body-s">{t('profile.spent')}</span>
          <Amount kind="coins" count={e.coins} size="s" />
        </p>
      ) : (
        <p className="gc-history-row__line">
          <Amount kind="points" count={e.points} size="s" signed />
          {e.coins !== 0 && <Amount kind="coins" count={e.coins} size="s" signed />}
          {e.bonus > 0 && <span className="gc-history-row__bonus gc-body-s">{t('profile.bonus', { count: e.bonus })}</span>}
          {e.rejected && <StatusChip tone="danger" icon="x">{t('profile.rejected')}</StatusChip>}
          {e.withdrawn && <StatusChip tone="muted" icon="x">{t('profile.withdrawn')}</StatusChip>}
        </p>
      )}
      {e.photo_id !== null && (
        <DeletePhoto key={e.photo_id} photoId={e.photo_id} undecided={e.photo_undecided} onDeleted={onDeleted} />
      )}
    </div>
  )
}
