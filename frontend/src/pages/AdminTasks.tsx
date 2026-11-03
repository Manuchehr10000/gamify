import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Lock, Printer } from 'lucide-react'
import { Link } from 'react-router-dom'
import { confirmed } from '../admin'
import { api, ApiError, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card, Screen } from '../components/ui'
import { hhmm, type Stage } from '../feed'
import type { Frozen } from '../rating'

type Schedule = { state: 'none' | 'before' | 'running' | 'over'; current: number | null; stages: Stage[] }
type Result = {
  stages_added: number
  stages_changed: number
  added: number
  changed: number
  hidden: number
  prizes_added: number
  prizes_changed: number
  prizes_hidden: number
  levels_changed: boolean
  // Any bad row refuses the whole file
  // A range or length the row broke comes with it (min, max, column), for the message
  failed: { sheet: string; row: number; reason: string; min?: number; max?: number; column?: string }[]
  // The preview: what the file adds, changes and hides
  items: { sheet: string; code: string; name: string; change: 'added' | 'changed' | 'hidden' }[]
}

export function AdminTasks() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('admin'))
  const [schedule, setSchedule] = useState<Schedule | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Result | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const fail = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('admin')
      setToken(null)
      return
    }
    const detail = err instanceof ApiError ? err.detail as { code?: string; items?: string[] } | string : null
    if (typeof detail === 'object' && detail?.code === 'missing') {
      setError(t('tasksAdmin.missing', { items: (detail.items ?? []).join(', ') }))
    } else if (detail === 'nobody_ranked') {
      setError(t('ratingAdmin.nobodyRanked'))
    } else if (detail === 'no_next_stage') {
      setError(t('tasksAdmin.noNextStage'))
    } else {
      setError(t('common.error'))
    }
  }, [t])

  useEffect(() => {
    if (token) api<Schedule>('/api/admin/stages', { token }).then(setSchedule).catch(fail)
  }, [token, fail])

  // First the preview: nothing changes until the admin presses «Применить», which sends the same file again
  async function send(path: string) {
    if (!file) return null
    const form = new FormData()
    form.append('file', file)
    return api<Result>(path, { token, form })
  }

  async function check(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setResult(null)
    setPreview(null)
    try {
      setPreview(await send('/api/admin/tasks/import/preview'))
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    setBusy(true)
    setError('')
    try {
      const applied = await send('/api/admin/tasks/import')
      // Something changed since the preview and a row no longer fits: the file is refused whole, as shown
      if (applied?.failed.length) {
        setPreview(applied)
        return
      }
      setResult(applied)
      setPreview(null)
      setSchedule(await api<Schedule>('/api/admin/stages', { token }))
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  async function nextStage() {
    setBusy(true)
    setError('')
    try {
      // The server says which stage ends and which starts; nothing changes until the admin agrees
      const next = await confirmed(t, (yes) =>
        api<Schedule>(`/api/admin/stages/advance${yes ? '?confirm=true' : ''}`, { token, method: 'POST' }))
      if (next) setSchedule(next)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  const current = schedule?.stages.find((s) => s.number === schedule.current)
  const canAdvance = schedule?.state === 'before' || (schedule?.state === 'running' && schedule.current !== schedule.stages.length)
  return (
    <Screen>
      <div className="flex flex-col gap-4 print:hidden">
        <h1 className="text-xl font-semibold">{t('tasksAdmin.title')}</h1>
        <Card className="flex flex-col gap-3">
          <p className="text-sm text-slate-600">{t('tasksAdmin.currentStage')}</p>
          <p className="text-lg font-semibold">
            {current
              ? `${current.number}. ${current.name} · ${hhmm(current.starts_at)}–${hhmm(current.ends_at)}`
              : t(`tasksAdmin.state.${schedule?.state ?? 'none'}`)}
          </p>
          {schedule && schedule.stages.length > 0 && (
            <ol className="text-sm text-slate-600">
              {schedule.stages.map((s) => (
                <li key={s.number} className={s.number === schedule.current ? 'font-medium text-slate-900' : ''}>
                  {s.number}. {s.name} · {hhmm(s.starts_at)}–{hhmm(s.ends_at)}
                </li>
              ))}
            </ol>
          )}
          <Button variant="outline" disabled={busy || !canAdvance} onClick={nextStage}>{t('tasksAdmin.next')}</Button>
        </Card>
        <Card>
          <form onSubmit={check} className="flex flex-col gap-4">
            <p className="text-sm text-slate-600">{t('tasksAdmin.uploadHint')}</p>
            <label className="flex cursor-pointer items-center gap-3 text-sm">
              <span className="rounded-lg bg-slate-100 px-3 py-2 font-medium hover:bg-slate-200">{t('admin.chooseFile')}</span>
              <span className="truncate text-slate-600">{file?.name ?? t('admin.noFile')}</span>
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="sr-only"
              />
            </label>
            <Button disabled={!file || busy}>{t('tasksAdmin.upload')}</Button>
          </form>
        </Card>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {preview && <Preview preview={preview} busy={busy} onApply={apply} onCancel={() => setPreview(null)} />}
        {result && (
          <Card className="flex flex-col gap-1">
            <p className="font-medium text-emerald-700">{t('tasksAdmin.applied')}</p>
            <p className="font-medium">{t('tasksAdmin.added', { count: result.added })}</p>
            <p className="text-slate-600">{t('tasksAdmin.changed', { count: result.changed })}</p>
            <p className="text-slate-600">{t('tasksAdmin.hidden', { count: result.hidden })}</p>
            {(result.stages_added > 0 || result.stages_changed > 0) && (
              <p className="text-slate-600">
                {t('tasksAdmin.stages', { added: result.stages_added, changed: result.stages_changed })}
              </p>
            )}
            {(result.prizes_added > 0 || result.prizes_changed > 0 || result.prizes_hidden > 0) && (
              <p className="text-slate-600">
                {t('tasksAdmin.prizes', {
                  added: result.prizes_added, changed: result.prizes_changed, hidden: result.prizes_hidden,
                })}
              </p>
            )}
            {result.levels_changed && <p className="text-slate-600">{t('tasksAdmin.levels')}</p>}
          </Card>
        )}
        <Button variant="outline" onClick={() => download('/api/admin/tasks/export', token, 'tasks.xlsx').catch(fail)}>
          {t('tasksAdmin.download')}
        </Button>
        <Link to="/admin/tasks/qr" className="text-center font-medium text-emerald-700 underline">{t('tasksAdmin.qrLink')}</Link>
      </div>
      <RatingFreeze token={token} fail={fail} />
    </Screen>
  )
}

function Preview({ preview, busy, onApply, onCancel }:
  { preview: Result; busy: boolean; onApply: () => void; onCancel: () => void }) {
  const { t } = useTranslation()
  if (preview.failed.length > 0) {
    return (
      <Card className="flex flex-col gap-2">
        <p className="font-medium text-red-700">{t('tasksAdmin.refused')}</p>
        <ul className="text-sm text-red-700">
          {preview.failed.map((f) => (
            <li key={`${f.sheet}-${f.row}-${f.reason}`}>
              {t('tasksAdmin.row', { sheet: f.sheet, row: f.row, reason: t(`tasksAdmin.reasons.${f.reason}`, { min: f.min, max: f.max, column: f.column }) })}
            </li>
          ))}
        </ul>
      </Card>
    )
  }
  return (
    <Card className="flex flex-col gap-3">
      <p className="font-medium">{t('tasksAdmin.preview.title')}</p>
      {preview.items.length === 0
        ? <p className="text-sm text-slate-600">{t('tasksAdmin.preview.none')}</p>
        : (
          <ul className="max-h-80 overflow-y-auto text-sm">
            {preview.items.map((i) => (
              <li key={`${i.sheet}-${i.code}-${i.change}`} className={i.change === 'hidden' ? 'text-amber-700' : 'text-slate-700'}>
                {i.sheet === 'Уровни'
                  ? t('tasksAdmin.preview.levels')
                  : t('tasksAdmin.preview.item', { sheet: i.sheet, code: i.code, name: i.name, change: t(`tasksAdmin.preview.change.${i.change}`) })}
              </li>
            ))}
          </ul>
        )}
      <div className="flex gap-3">
        <Button disabled={busy || preview.items.length === 0} onClick={onApply}>{t('tasksAdmin.preview.apply')}</Button>
        <Button variant="outline" disabled={busy} onClick={onCancel}>{t('tasksAdmin.preview.cancel')}</Button>
      </div>
    </Card>
  )
}

// Freezing keeps the places for the ceremony; the host reads the printed top 10
function RatingFreeze({ token, fail }: { token: string; fail: (err: unknown) => void }) {
  const { t } = useTranslation()
  const [state, setState] = useState<Frozen | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // frozen: null only reads the state and the frozen list; it never freezes
    api<Frozen>('/api/admin/rating/freeze', { token, json: { frozen: null } }).then(setState).catch(fail)
  }, [token, fail])

  async function toggle(frozen: boolean) {
    if (!window.confirm(t(frozen ? 'ratingAdmin.confirmFreeze' : 'ratingAdmin.confirmUnfreeze'))) return
    setBusy(true)
    try {
      setState(await api<Frozen>('/api/admin/rating/freeze', { token, json: { frozen } }))
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  if (!state) return null
  return (
    <Card className="flex flex-col gap-3 print:p-0 print:shadow-none print:ring-0">
      <div className="flex flex-col gap-3 print:hidden">
        <h2 className="text-lg font-semibold">{t('ratingAdmin.title')}</h2>
        <p className="flex items-start gap-2 text-sm text-slate-600">
          {state.frozen && <Lock className="mt-0.5 size-4 shrink-0 text-emerald-700" aria-hidden />}
          {t(state.frozen ? 'ratingAdmin.frozenNote' : 'ratingAdmin.live')}
        </p>
        {state.frozen
          ? <Button variant="outline" disabled={busy} onClick={() => toggle(false)}>{t('ratingAdmin.unfreeze')}</Button>
          : <Button disabled={busy} onClick={() => toggle(true)}>{t('ratingAdmin.freeze')}</Button>}
      </div>
      {state.frozen && (
        <>
          <div className="mt-2 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">{t('ratingAdmin.listTitle')}</h2>
            <Button variant="outline" className="h-10 print:hidden" onClick={() => window.print()} disabled={!state.top.length}>
              <Printer className="mr-2 size-4" aria-hidden />
              {t('ratingAdmin.print')}
            </Button>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1 pr-2 font-medium">{t('ratingAdmin.place')}</th>
                <th className="py-1 pr-2 font-medium">{t('ratingAdmin.name')}</th>
                <th className="py-1 pr-2 font-medium">{t('ratingAdmin.company')}</th>
                <th className="py-1 text-right font-medium">{t('ratingAdmin.points')}</th>
              </tr>
            </thead>
            <tbody>
              {state.top.map((r) => (
                <tr key={r.place} className="border-t border-slate-200">
                  <td className="py-2 pr-2 tabular-nums">{r.place}</td>
                  <td className="py-2 pr-2 font-medium">{`${r.last_name} ${r.first_name}`.trim()}</td>
                  <td className="py-2 pr-2">{r.company}</td>
                  <td className="py-2 text-right tabular-nums">{r.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  )
}
