import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { LevelUp, Reward, ReviewNote, StageBanner, StageBar, TaskTypeTag, Wallet } from '../components/console/game'
import { BADGE_GLYPHS, type IconName } from '../components/console/glyphs'
import { Callout, Loading, MessageCard, NavRow, PageHeader, Screen, StatusChip } from '../components/console/ui'
import { cache, hhmm, type Feed as FeedData, type Stage, type Task } from '../feed'
import { forgetUpload, isWaiting, onSent, useUpload } from '../uploads'
import { useConfigVersion } from '../version'

// The stage can change at any moment (by the clock or the admin's button): ask again well inside a minute
const POLL_MS = 30_000

type Moment = { title: string; icon?: IconName }

type State =
  | { kind: 'loading' }
  | { kind: 'loggedOut' }
  | { kind: 'error' }
  | { kind: 'ready'; feed: FeedData; offline: boolean }

export function Feed() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))
  const [banner, setBanner] = useState<Stage | null>(null)
  // The level just reached, then each badge just earned, one after the other. The server sends them once,
  // so only a fresh load (never the saved copy) shows them
  const [moments, setMoments] = useState<Moment[]>([])

  const load = useCallback(async () => {
    const token = tokens.get('guest')
    if (!token) return
    try {
      const feed = await api<FeedData>('/api/feed', { token })
      cache.saveFeed({ ...feed, new_level: null, new_badges: [] })
      const fresh: Moment[] = [
        ...(feed.new_level ? [{ title: t('level.new', { name: feed.new_level }) }] : []),
        ...feed.new_badges.map((b) => ({ title: t('badges.new', { name: t(`badges.${b}.name`) }), icon: BADGE_GLYPHS[b] })),
      ]
      if (fresh.length) setMoments((shown) => [...shown, ...fresh])
      // A photo sent back for a retake: the earlier upload's «Выполнено» no longer holds
      feed.tasks.filter((task) => task.review === 'retake').forEach((task) => forgetUpload(task.id))
      if (feed.stage) {
        const last = cache.lastStage()
        if (last !== null && last !== feed.stage.number) setBanner(feed.stage)
        cache.saveStage(feed.stage.number)
      }
      setState({ kind: 'ready', feed, offline: false })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        tokens.clear('guest')
        setState({ kind: 'loggedOut' })
        return
      }
      const saved = cache.feed()
      setState(saved ? { kind: 'ready', feed: saved, offline: true } : { kind: 'error' })
    }
  }, [t])

  useEffect(() => {
    // The first load and the timer both refresh the feed from outside React's render
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
    const timer = setInterval(load, POLL_MS)
    const wake = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('online', load)
    const stopSent = onSent(load)
    return () => {
      stopSent()
      clearInterval(timer)
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('online', load)
    }
  }, [load])

  // An admin's change (points, a task switched off, the stage) shows within 10 seconds
  useConfigVersion(load)

  useEffect(() => {
    if (!banner) return
    const timer = setTimeout(() => setBanner(null), 8000)
    return () => clearTimeout(timer)
  }, [banner])

  if (state.kind === 'loading') return <Screen><Loading /></Screen>
  if (state.kind === 'loggedOut' || state.kind === 'error') {
    return (
      <Screen>
        <MessageCard icon="alert" title={t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')} />
      </Screen>
    )
  }

  const { feed, offline } = state
  return (
    <Screen>
      {moments.length > 0 && (
        <LevelUp key={moments[0].title} title={moments[0].title} icon={moments[0].icon} onClose={() => setMoments((m) => m.slice(1))} />
      )}
      <PageHeader title={t('common.title')} />
      {offline && <Callout tone="offline">{t('feed.offline')}</Callout>}
      {banner && <StageBanner stage={banner} onClose={() => setBanner(null)} />}
      <Wallet feed={feed} />
      <NavRow to="/market" icon="bag" tone="market" label={t('feed.toMarket')} />
      <NavRow to="/app/rating" icon="trophy" label={t('feed.toRating')} />
      <Body feed={feed} />
    </Screen>
  )
}

function Body({ feed }: { feed: FeedData }) {
  const { t } = useTranslation()
  if (feed.state === 'over') return <MessageCard icon="trophy" title={t('feed.over')} />
  if (feed.state !== 'running' || !feed.stage) {
    const text = feed.starts_at ? t('feed.before', { time: hhmm(feed.starts_at) }) : t('feed.soon')
    return <MessageCard icon="clock" title={text} />
  }
  return (
    <>
      <StageBar stage={feed.stage} count={feed.stage_count} />
      {feed.tasks.length === 0 && <MessageCard title={t('feed.empty')} />}
      <ul className="flex flex-col gap-3">
        {feed.tasks.map((task) => (
          <li key={task.id}><TaskCard task={task} /></li>
        ))}
      </ul>
    </>
  )
}

// Whole minutes until a window closes, rounded up; the feed reloads every 30 s, so it stays current
const minutesLeft = (iso: string) => Math.max(1, Math.ceil((new Date(iso).getTime() - Date.now()) / 60_000))

// What the server answers when a send can't count
const REFUSALS = new Set(['stage_closed', 'time_up', 'claim_lapsed', 'limit'])

function TaskCard({ task: fromFeed }: { task: Task }) {
  const { t } = useTranslation()
  const upload = useUpload(fromFeed.id)
  // A photo or text that just went through counts at once, before the next feed load
  const task = upload?.state === 'sent' && upload.award.result !== 'unavailable' ? upload.award.task : fromFeed
  const sending = isWaiting(upload)
  // Refused by the server: the card says why until the guest has seen it on the task
  const refused = !task.done && upload?.state === 'failed' && REFUSALS.has(upload.reason) ? upload.reason : ''
  const deadline = task.window_end && !task.done
    ? task.method === 'quiz' ? t('feed.closesIn', { count: minutesLeft(task.window_end) }) : t('feed.closesAt', { time: hhmm(task.window_end) })
    : undefined
  const edge = task.review === 'penalty' ? 'gc-task-card--rejected' : task.done ? 'gc-task-card--done' : ''
  return (
    <Link to={`/app/tasks/${task.id}`} className={`gc-task-card ${edge}`}>
      <TaskTypeTag task={task} deadline={deadline} />
      <p className="gc-task-card__text gc-body">{task.text}</p>
      {!sending && <ReviewNote task={task} />}
      <div className="gc-task-card__foot">
        <Reward task={task} />
        <span className="gc-task-card__status">
          {task.done && task.review === 'penalty' && <StatusChip tone="danger" icon="x">{t('review.rejected')}</StatusChip>}
          {task.done && task.review !== 'penalty' && <StatusChip tone="success" icon="check">{t('feed.done')}</StatusChip>}
          {!task.done && upload?.state === 'sending' && <StatusChip tone="muted">{t('submit.uploading')}</StatusChip>}
          {!task.done && (upload?.state === 'unclaimed' || upload?.state === 'claimed') && (
            <StatusChip tone="warning" icon="wifi-off">{t(`submit.${upload.state}`)}</StatusChip>
          )}
          {refused && <StatusChip tone="danger" icon="x">{t(`submit.errors.${refused}`)}</StatusChip>}
        </span>
      </div>
    </Link>
  )
}
