import { Check, ChevronLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { TaskIcon } from '../components/TaskIcon'
import { Button, Card, Screen } from '../components/ui'
import { cache, type Task } from '../feed'
import { PartnerBadge, Reward } from './Feed'

type State = { kind: 'loading' } | { kind: 'missing' } | { kind: 'ready'; task: Task }

export function TaskDetail() {
  const { t } = useTranslation()
  const id = Number(useParams().id)
  // Open at once from the feed's copy; the server's answer replaces it
  const [state, setState] = useState<State>(() => {
    const saved = cache.task(id)
    return saved ? { kind: 'ready', task: saved } : { kind: 'loading' }
  })

  useEffect(() => {
    api<Task>(`/api/tasks/${id}`, { token: tokens.get('guest') })
      .then((task) => setState({ kind: 'ready', task }))
      .catch((err) => {
        if (err instanceof ApiError) setState({ kind: 'missing' })
        // Offline: keep the feed's copy if there is one
        else setState((s) => (s.kind === 'loading' ? { kind: 'missing' } : s))
      })
  }, [id])

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
          {state.task.done ? (
            <p className="flex items-center justify-center gap-1 py-3 font-medium text-emerald-700">
              <Check className="size-5" aria-hidden />
              {t('feed.done')}
            </p>
          ) : (
            <Button disabled>{t('task.doSoon')}</Button>
          )}
        </Card>
      )}
    </Screen>
  )
}
