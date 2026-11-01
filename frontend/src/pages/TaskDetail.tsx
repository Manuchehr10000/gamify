import { Check, ChevronLeft, ExternalLink, QrCode, ShoppingBag } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { AwardView } from '../components/AwardView'
import { TaskIcon } from '../components/TaskIcon'
import { Button, Card, Screen } from '../components/ui'
import { cache, type Award, type Task } from '../feed'
import { PartnerBadge, Reward } from './Feed'

type State = { kind: 'loading' } | { kind: 'missing' } | { kind: 'ready'; task: Task }

function Action({ task, onAward }: { task: Task; onAward: (a: Award) => void }) {
  const { t } = useTranslation()
  const [opened, setOpened] = useState(() => cache.linkOpened(task.id))
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (task.done) {
    return (
      <p className="flex items-center justify-center gap-1 py-3 font-medium text-emerald-700">
        <Check className="size-5" aria-hidden />
        {t('feed.done')}
      </p>
    )
  }
  if (task.method === 'qr') {
    return (
      <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-emerald-800">
        <QrCode className="size-5 shrink-0" aria-hidden />
        {t('task.scanHint')}
      </p>
    )
  }
  if (task.method === 'market') {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-slate-700">{t('task.marketHint')}</p>
        <Link to="/market" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 font-medium text-white">
          <ShoppingBag className="size-4" aria-hidden />
          {t('task.toMarket')}
        </Link>
      </div>
    )
  }
  if (task.method !== 'link') return <Button disabled>{t('task.doSoon')}</Button>

  async function confirm() {
    setBusy(true)
    setError('')
    try {
      onAward(await api<Award>(`/api/tasks/${task.id}/complete`, { token: tokens.get('guest'), method: 'POST' }))
    } catch {
      setError(t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <a
        href={task.link}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => {
          cache.markLinkOpened(task.id)
          setOpened(true)
        }}
        className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 font-medium text-white"
      >
        {t('task.do')}
        <ExternalLink className="size-4" aria-hidden />
      </a>
      {opened && (
        <>
          <label className="flex items-center gap-3 text-base">
            <input type="checkbox" className="size-5 accent-emerald-600" checked={ticked} onChange={(e) => setTicked(e.target.checked)} />
            {t('task.registered')}
          </label>
          <Button variant="outline" disabled={!ticked || busy} onClick={confirm}>{t('task.confirm')}</Button>
        </>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

export function TaskDetail() {
  const { t } = useTranslation()
  const id = Number(useParams().id)
  // Open at once from the feed's copy; the server's answer replaces it
  const [state, setState] = useState<State>(() => {
    const saved = cache.task(id)
    return saved ? { kind: 'ready', task: saved } : { kind: 'loading' }
  })
  const [award, setAward] = useState<Award | null>(null)

  useEffect(() => {
    api<Task>(`/api/tasks/${id}`, { token: tokens.get('guest') })
      .then((task) => setState({ kind: 'ready', task }))
      .catch((err) => {
        if (err instanceof ApiError) setState({ kind: 'missing' })
        // Offline: keep the feed's copy if there is one
        else setState((s) => (s.kind === 'loading' ? { kind: 'missing' } : s))
      })
  }, [id])

  if (award) return <Screen><AwardView award={award} /></Screen>

  return (
    <Screen>
      <Link to="/app" className="flex items-center gap-1 text-sm font-medium text-slate-600">
        <ChevronLeft className="size-4" aria-hidden />
        {t('feed.toFeed')}
      </Link>
      {state.kind === 'loading' && <p className="text-center text-slate-500">{t('common.loading')}</p>}
      {state.kind === 'missing' && <Card className="text-center text-lg font-medium">{t('task.missing')}</Card>}
      {state.kind === 'ready' && (
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <TaskIcon type={state.task.type} className="size-5 text-emerald-700" />
            <span>{t(`types.${state.task.type}`)}</span>
            {state.task.partner_name && <PartnerBadge name={state.task.partner_name} />}
          </div>
          <p className="whitespace-pre-line text-lg leading-relaxed">{state.task.text}</p>
          <Reward task={state.task} />
          <Action task={state.task} onAward={setAward} />
        </Card>
      )}
    </Screen>
  )
}
