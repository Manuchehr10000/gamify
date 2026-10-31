import { Check, Coins, Star, Trophy, WifiOff, X } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { DayBar } from '../components/DayBar'
import { TaskIcon } from '../components/TaskIcon'
import { Card, Screen } from '../components/ui'
import { cache, hhmm, type Feed as FeedData, type Stage, type Task } from '../feed'

// The stage can change at any moment (by the clock or the admin's button): ask again well inside a minute
const POLL_MS = 30_000

type State =
  | { kind: 'loading' }
  | { kind: 'loggedOut' }
  | { kind: 'error' }
  | { kind: 'ready'; feed: FeedData; offline: boolean }

export function Feed() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))
  const [banner, setBanner] = useState<Stage | null>(null)

  const load = useCallback(async () => {
    const token = tokens.get('guest')
    if (!token) return
    try {
      const feed = await api<FeedData>('/api/feed', { token })
      cache.saveFeed(feed)
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
  }, [])

  useEffect(() => {
    // The first load and the timer both refresh the feed from outside React's render
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
    const timer = setInterval(load, POLL_MS)
    const wake = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('online', load)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('online', load)
    }
  }, [load])

  useEffect(() => {
    if (!banner) return
    const timer = setTimeout(() => setBanner(null), 8000)
    return () => clearTimeout(timer)
  }, [banner])

  if (state.kind === 'loading') return <Screen><p className="text-center text-slate-500">{t('common.loading')}</p></Screen>
  if (state.kind === 'loggedOut' || state.kind === 'error') {
    return (
      <Screen>
        <Card className="text-center text-lg font-medium">
          {t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')}
        </Card>
      </Screen>
    )
  }

  const { feed, offline } = state
  return (
    <Screen>
      {offline && (
        <p className="flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-2 text-sm text-amber-800">
          <WifiOff className="size-4 shrink-0" aria-hidden />
          {t('feed.offline')}
        </p>
      )}
      {banner && (
        <div className="flex items-start gap-3 rounded-2xl bg-emerald-600 p-4 text-white shadow-md" role="status">
          <div className="flex-1">
            <p className="font-semibold">{t('feed.newStage', { name: banner.name })}</p>
            {banner.message && <p className="mt-1 text-sm text-emerald-50">{banner.message}</p>}
          </div>
          <button onClick={() => setBanner(null)} aria-label={t('feed.close')} className="-m-1 p-1">
            <X className="size-5" aria-hidden />
          </button>
        </div>
      )}
      <Body feed={feed} />
    </Screen>
  )
}

function Body({ feed }: { feed: FeedData }) {
  const { t } = useTranslation()
  if (feed.state === 'over') return <Notice icon={<Trophy className="size-8" />} text={t('feed.over')} />
  if (feed.state !== 'running' || !feed.stage) {
    const text = feed.starts_at ? t('feed.before', { time: hhmm(feed.starts_at) }) : t('feed.soon')
    return <Notice text={text} />
  }
  return (
    <>
      <DayBar stage={feed.stage} count={feed.stage_count} />
      {feed.tasks.length === 0 && <p className="py-8 text-center text-slate-500">{t('feed.empty')}</p>}
      <ul className="flex flex-col gap-3">
        {feed.tasks.map((task) => (
          <li key={task.id}><TaskCard task={task} /></li>
        ))}
      </ul>
    </>
  )
}

function Notice({ text, icon }: { text: string; icon?: ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-3 py-12 text-center text-lg font-medium">
      {icon && <span className="text-emerald-600">{icon}</span>}
      {text}
    </Card>
  )
}

export function Reward({ task }: { task: Task }) {
  const { t } = useTranslation()
  return (
    <span className="flex items-center gap-3 text-sm font-medium">
      <span className="text-emerald-700">{t('feed.points', { count: task.points })}</span>
      <span className="flex items-center gap-1 text-amber-700">
        <Coins className="size-4" aria-hidden />
        {t('feed.coins', { count: task.coins })}
      </span>
    </span>
  )
}

export function PartnerBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
      <Star className="size-3 fill-current" aria-hidden />
      {name}
    </span>
  )
}

function TaskCard({ task }: { task: Task }) {
  const { t } = useTranslation()
  return (
    <Link
      to={`/app/tasks/${task.id}`}
      className={`flex flex-col gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 transition active:scale-[0.99] ${task.done ? 'ring-emerald-200' : 'ring-slate-200'}`}
    >
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <TaskIcon type={task.type} className="size-4 text-emerald-700" />
        <span>{t(`types.${task.type}`)}</span>
        {task.partner_name && <PartnerBadge name={task.partner_name} />}
        {task.window_end && !task.done && (
          <span className="text-xs text-red-600">{t('feed.closesAt', { time: hhmm(task.window_end) })}</span>
        )}
      </div>
      <p className="line-clamp-3 text-base">{task.text}</p>
      <div className="flex items-center justify-between">
        <Reward task={task} />
        {task.done && (
          <span className="flex items-center gap-1 text-sm font-medium text-emerald-700">
            <Check className="size-4" aria-hidden />
            {t('feed.done')}
          </span>
        )}
      </div>
    </Link>
  )
}
