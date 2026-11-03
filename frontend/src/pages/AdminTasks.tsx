import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { AdminShell, DataTable, FileUpload, StageSchedule } from '../components/console/admin'
import { InlineConfirm, SectionHeading } from '../components/console/rewards'
import { Button, Callout, Card, Icon } from '../components/console/ui'
import type { Stage } from '../feed'
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
  // The next-stage question in the stage card, naming the stage that ends and the one that starts
  const [asking, setAsking] = useState<string | null>(null)

  const fail = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('admin')
      setToken(null)
      return
    }
    const detail = err instanceof ApiError ? err.detail as { code?: string; items?: string[] } | string : null
    if (typeof detail === 'object' && detail?.code === 'missing') {
      setError(t('tasksAdmin.missing', { items: (detail.items ?? []).join(', ') }))
    } else if (typeof detail === 'object' && detail?.code === 'stale') {
      setError(t('settingsAdmin.errors.stale'))
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

  // First ask the server what would change (without confirm it changes nothing), then ask the admin in the card
  async function askNext() {
    setBusy(true)
    setError('')
    try {
      setSchedule(await api<Schedule>('/api/admin/stages/advance', { token, method: 'POST' }))
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail as { code?: string; impact?: { from: number | null; to: number | null }[] } : null
      if (err instanceof ApiError && err.status === 409 && detail?.code === 'confirm') {
        const none = t('settingsAdmin.stageNone')
        const lines = (detail.impact ?? []).map((i) => t('settingsAdmin.impact.stage_change', { from: i.from ?? none, to: i.to ?? none }))
        setAsking([t('tasksAdmin.confirmNext'), ...lines].join(' '))
      } else {
        fail(err)
      }
    } finally {
      setBusy(false)
    }
  }

  // Called only after the admin said yes in the stage card; «Отмена» never sends the confirm
  async function nextStage() {
    setAsking(null)
    setBusy(true)
    setError('')
    try {
      setSchedule(await api<Schedule>('/api/admin/stages/advance?confirm=true', { token, method: 'POST' }))
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  return (
    <AdminShell
      title={t('tasksAdmin.title')}
      actions={(
        <>
          <Button variant="outline" icon="download" block={false} onClick={() => download('/api/admin/tasks/export', token, 'tasks.xlsx').catch(fail)}>
            {t('tasksAdmin.download')}
          </Button>
          <Button variant="outline" icon="qr" block={false} to="/admin/tasks/qr">{t('tasksAdmin.qrLink')}</Button>
        </>
      )}
    >
      {/* Printing this page gives the frozen top 10 only */}
      <div className="gc-admin-shell__body gc-no-print">
        {error && <Callout tone="danger">{error}</Callout>}
        <StageSchedule
          schedule={schedule}
          busy={busy}
          asking={asking}
          onAsk={askNext}
          onCancel={() => setAsking(null)}
          onAdvance={nextStage}
        />
        <Card>
          <form onSubmit={check} className="gc-admin-form" aria-busy={busy || undefined}>
            <p className="gc-admin-note gc-body-s">{t('tasksAdmin.uploadHint')}</p>
            <FileUpload
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              fileName={file?.name}
              busy={busy}
              onChange={setFile}
            />
            <Button type="submit" busy={busy} disabled={!file}>{t('tasksAdmin.upload')}</Button>
          </form>
        </Card>
        {preview && <Preview preview={preview} busy={busy} onApply={apply} onCancel={() => setPreview(null)} />}
        {result && (
          <Callout tone="success">
            <p className="gc-label">{t('tasksAdmin.applied')}</p>
            <p>{t('tasksAdmin.added', { count: result.added })}</p>
            <p>{t('tasksAdmin.changed', { count: result.changed })}</p>
            <p>{t('tasksAdmin.hidden', { count: result.hidden })}</p>
            {(result.stages_added > 0 || result.stages_changed > 0) && (
              <p>{t('tasksAdmin.stages', { added: result.stages_added, changed: result.stages_changed })}</p>
            )}
            {(result.prizes_added > 0 || result.prizes_changed > 0 || result.prizes_hidden > 0) && (
              <p>
                {t('tasksAdmin.prizes', {
                  added: result.prizes_added, changed: result.prizes_changed, hidden: result.prizes_hidden,
                })}
              </p>
            )}
            {result.levels_changed && <p>{t('tasksAdmin.levels')}</p>}
          </Callout>
        )}
      </div>
      <RatingFreeze token={token} fail={fail} />
    </AdminShell>
  )
}

function Preview({ preview, busy, onApply, onCancel }:
  { preview: Result; busy: boolean; onApply: () => void; onCancel: () => void }) {
  const { t } = useTranslation()
  // A bad row refuses the whole file: one red strip naming every bad row
  if (preview.failed.length > 0) {
    return (
      <Callout tone="danger">
        <p className="gc-label">{t('tasksAdmin.refused')}</p>
        <ul>
          {preview.failed.map((f) => (
            <li key={`${f.sheet}-${f.row}-${f.reason}`}>
              {t('tasksAdmin.row', { sheet: f.sheet, row: f.row, reason: t(`tasksAdmin.reasons.${f.reason}`, { min: f.min, max: f.max, column: f.column }) })}
            </li>
          ))}
        </ul>
      </Callout>
    )
  }
  return (
    <Card>
      <p className="gc-label">{t('tasksAdmin.preview.title')}</p>
      {preview.items.length === 0
        ? <p className="gc-admin-note gc-body-s">{t('tasksAdmin.preview.none')}</p>
        : (
          <ul className="gc-list-group gc-admin-preview gc-body-s">
            {preview.items.map((i) => (
              <li key={`${i.sheet}-${i.code}-${i.change}`} className={i.change === 'hidden' ? 'gc-admin-preview__item--hidden' : ''}>
                {i.sheet === 'Уровни'
                  ? t('tasksAdmin.preview.levels')
                  : t('tasksAdmin.preview.item', { sheet: i.sheet, code: i.code, name: i.name, change: t(`tasksAdmin.preview.change.${i.change}`) })}
              </li>
            ))}
          </ul>
        )}
      <div className="gc-admin-pair">
        <Button variant="outline" disabled={busy} onClick={onCancel}>{t('tasksAdmin.preview.cancel')}</Button>
        <Button busy={busy} disabled={preview.items.length === 0} onClick={onApply}>{t('tasksAdmin.preview.apply')}</Button>
      </div>
    </Card>
  )
}

// Freezing keeps the places for the ceremony; the host reads the printed top 10
function RatingFreeze({ token, fail }: { token: string; fail: (err: unknown) => void }) {
  const { t } = useTranslation()
  const [state, setState] = useState<Frozen | null>(null)
  const [busy, setBusy] = useState(false)
  // Freezing or unfreezing asks in the card first
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    // frozen: null only reads the state and the frozen list; it never freezes
    api<Frozen>('/api/admin/rating/freeze', { token, json: { frozen: null } }).then(setState).catch(fail)
  }, [token, fail])

  async function toggle(frozen: boolean) {
    setAsking(false)
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
    <Card>
      <div className="gc-admin-shell__body gc-no-print">
        <SectionHeading>{t('ratingAdmin.title')}</SectionHeading>
        <p className={`gc-admin-note gc-body-s ${state.frozen ? 'gc-admin-note--icon' : ''}`}>
          {state.frozen && <Icon name="lock" size={16} />}
          <span>{t(state.frozen ? 'ratingAdmin.frozenNote' : 'ratingAdmin.live')}</span>
        </p>
        {asking
          ? (
            <InlineConfirm
              question={t(state.frozen ? 'ratingAdmin.confirmUnfreeze' : 'ratingAdmin.confirmFreeze')}
              busy={busy}
              onCancel={() => setAsking(false)}
              onConfirm={() => toggle(!state.frozen)}
            />
          )
          : state.frozen
            ? <Button variant="outline" busy={busy} onClick={() => setAsking(true)}>{t('ratingAdmin.unfreeze')}</Button>
            : <Button busy={busy} onClick={() => setAsking(true)}>{t('ratingAdmin.freeze')}</Button>}
      </div>
      {state.frozen && (
        <>
          <div className="gc-admin-head-row">
            <SectionHeading>{t('ratingAdmin.listTitle')}</SectionHeading>
            <Button variant="outline" icon="printer" block={false} onClick={() => window.print()} disabled={!state.top.length}>
              {t('ratingAdmin.print')}
            </Button>
          </div>
          <DataTable
            columns={[
              { key: 'place', label: t('ratingAdmin.place'), align: 'right' },
              { key: 'name', label: t('ratingAdmin.name') },
              { key: 'company', label: t('ratingAdmin.company') },
              { key: 'points', label: t('ratingAdmin.points'), align: 'right' },
            ]}
            rows={state.top.map((r) => ({
              id: r.place, place: r.place, name: `${r.last_name} ${r.first_name}`.trim(), company: r.company || null, points: r.points,
            }))}
          />
        </>
      )}
    </Card>
  )
}
