import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import type { TFunction } from 'i18next'
import { confirmed, usePhotoDeletion } from '../admin'
import { api, ApiError, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { THEMES, usePreviewFonts, type Skin } from '../components/console/skin'
import { Card as ConsoleCard, Stripe } from '../components/console/ui'
import { Button, Card, Input } from '../components/ui'

const API_URL = import.meta.env.VITE_API_URL ?? ''

type Kind = 'stages' | 'tasks' | 'prizes' | 'questions' | 'levels' | 'partners' | 'staff' | 'push' | 'badges'
type Tab = Kind | 'settings' | 'log'
const TABS: Tab[] = ['stages', 'tasks', 'prizes', 'questions', 'levels', 'partners', 'staff', 'push', 'badges', 'settings', 'log']

type Value = string | number | boolean | null
type Field = {
  name: string
  // multiplier: 1 to 5 in steps of 0.5 (a stage's «Множитель»)
  type: 'int' | 'text' | 'bool' | 'datetime' | 'choice' | 'ref' | 'secret' | 'multiplier'
  required: boolean
  min: number | null
  max: number | null
  choices: string[]
  options: { id: number; label: string; active: boolean }[] | null
  effect: 'now' | 'recheck' | 'locked'
  fixed: boolean
}
type Row = { id: number; version: number; values: Record<string, Value>; extra: Record<string, Value> }
type List = { fields: Field[]; rows: Row[] }
// text: a text setting's value (min and max are then its length); null for a number. choices: the ids a choice
// setting (the skin) takes
type Setting = {
  key: string; value: number; min: number; max: number; effect: Field['effect']; integer: boolean; text: string | null
  choices: string[] | null; version: number
}
// The push switch and texts show on the «Push» tab, not with the other settings
const isPush = (key: string) => key.startsWith('push_')
// What the form field starts with: the number, or a text setting's text (the photo deletion date)
const draft = (s: Setting) => (s.text === null ? String(s.value) : s.text)
type Event = {
  id: number
  created_at: string
  staff_name: string
  kind: string
  item: string
  field: string
  old_value: string | null
  new_value: string | null
  source: 'form' | 'excel'
}

// The columns each list shows; the form shows every field
const COLUMNS: Record<Kind, string[]> = {
  stages: ['number', 'name', 'starts_at', 'ends_at', 'market', 'batch_size', 'multiplier', 'active'],
  tasks: ['code', 'stage_id', 'type', 'text', 'points', 'coins', 'method', 'limit', 'active'],
  prizes: ['code', 'name', 'partner_id', 'price', 'quantity', 'active'],
  questions: ['task_id', 'number', 'text', 'correct'],
  levels: ['name', 'min_points'],
  partners: ['name', 'package', 'active'],
  staff: ['name', 'role', 'active'],
  push: ['at', 'kind', 'title', 'text', 'state'],
  badges: ['code', 'name', 'rule', 'count', 'kinds', 'coins', 'on_screen', 'active'],
}

const when = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Dushanbe',
})

type Detail = { code?: string; field?: string; min?: number; max?: number }

// The server names the field and the range; the message says it in Russian
function errorText(t: TFunction, err: unknown, label: (field: string) => string): string {
  const detail = err instanceof ApiError ? err.detail as Detail | string : null
  const code = typeof detail === 'string' ? detail : detail?.code
  if (!code) return t('common.error')
  const extra = typeof detail === 'object' && detail ? detail : {}
  return t(`settingsAdmin.errors.${code}`, {
    defaultValue: t('common.error'), ...extra, field: extra.field ? label(extra.field) : '',
  })
}

export function AdminSettings() {
  const [token, setToken] = useState(tokens.get('admin'))
  const [tab, setTab] = useState<Tab>('tasks')

  const loggedOut = useCallback(() => {
    tokens.clear('admin')
    setToken(null)
  }, [])

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />
  return <SettingsPage token={token} tab={tab} setTab={setTab} loggedOut={loggedOut} />
}

function SettingsPage({ token, tab, setTab, loggedOut }:
  { token: string; tab: Tab; setTab: (tab: Tab) => void; loggedOut: () => void }) {
  const { t } = useTranslation()
  // The same notice as the other admin pages: once it shows, the deletion date is locked
  const { notice: deletion, locked: dateLocked } = usePhotoDeletion()

  return (
    <main className="min-h-dvh bg-slate-50 px-4 py-8 text-slate-900">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
        <h1 className="text-xl font-semibold">{t('settingsAdmin.title')}</h1>
        {deletion && (
          <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900 ring-1 ring-amber-200">{deletion}</p>
        )}
        <nav className="flex flex-wrap gap-2">
          {TABS.map((k) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`rounded-lg px-3 py-2 text-sm font-medium ${tab === k ? 'bg-emerald-600 text-white' : 'bg-white ring-1 ring-slate-200 hover:bg-slate-100'}`}
            >
              {t(`settingsAdmin.tabs.${k}`)}
            </button>
          ))}
        </nav>
        {tab === 'settings' && <Settings token={token} loggedOut={loggedOut} dateLocked={dateLocked} />}
        {tab === 'push' && <PushSettings token={token} loggedOut={loggedOut} />}
        {tab === 'log' && <Log token={token} loggedOut={loggedOut} />}
        {tab !== 'settings' && tab !== 'log' && tab !== 'push' && <ListTab key={tab} kind={tab} token={token} loggedOut={loggedOut} />}
      </div>
    </main>
  )
}

type TabProps = { token: string; loggedOut: () => void }

function useFail(loggedOut: () => void, setError: (s: string) => void, label: (f: string) => string) {
  const { t } = useTranslation()
  return useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) loggedOut()
    else setError(errorText(t, err, label))
  }, [t, loggedOut, setError, label])
}

function ListTab({ kind, token, loggedOut }: TabProps & { kind: Kind }) {
  const { t } = useTranslation()
  const [list, setList] = useState<List | null>(null)
  // null: no form open · 'new': adding · a row: editing it
  const [editing, setEditing] = useState<Row | 'new' | null>(null)
  const [error, setError] = useState('')
  const label = useCallback((f: string) => t(`settingsAdmin.fields.${kind}.${f}`), [t, kind])
  const fail = useFail(loggedOut, setError, label)

  const load = useCallback(() => {
    api<List>(`/api/admin/lists/${kind}`, { token }).then(setList).catch(fail)
  }, [kind, token, fail])

  useEffect(load, [load])

  // «Отправить сейчас»: any push, whatever its time or state
  async function sendNow(row: Row) {
    if (!window.confirm(t('settingsAdmin.push.confirmSend', { item: String(row.values.title) }))) return
    setError('')
    try {
      await api(`/api/admin/push/${row.id}/send`, { token, method: 'POST' })
      load()
    } catch (err) {
      fail(err)
    }
  }

  async function remove(row: Row) {
    if (!window.confirm(t('settingsAdmin.confirmDelete', { item: String(row.values[COLUMNS[kind][0]]) }))) return
    setError('')
    try {
      const done = await confirmed(t, (yes) =>
        api(`/api/admin/lists/${kind}/${row.id}${yes ? '?confirm=true' : ''}`, { token, method: 'DELETE' }))
      if (done !== null) load()
    } catch (err) {
      fail(err)
    }
  }

  if (!list) return error ? <p className="text-sm text-red-600">{error}</p> : <p className="text-slate-500">{t('common.loading')}</p>
  const fields = Object.fromEntries(list.fields.map((f) => [f.name, f]))
  return (
    <div className="flex flex-col gap-4">
      {editing === null && <Button className="self-start" onClick={() => setEditing('new')}>{t('settingsAdmin.add')}</Button>}
      {editing !== null && (
        <RowForm
          key={editing === 'new' ? 'new' : editing.id}
          kind={kind}
          token={token}
          fields={list.fields}
          row={editing === 'new' ? null : editing}
          onDone={() => {
            setEditing(null)
            load()
          }}
          onCancel={() => setEditing(null)}
          loggedOut={loggedOut}
        />
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Card className="overflow-x-auto p-0">
        {list.rows.length === 0
          ? <p className="p-6 text-sm text-slate-500">{t('settingsAdmin.empty')}</p>
          : (
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  {kind === 'partners' && <th className="px-3 py-2 font-medium">{t('settingsAdmin.logo')}</th>}
                  {COLUMNS[kind].map((c) => <th key={c} className="px-3 py-2 font-medium">{label(c)}</th>)}
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.rows.map((row) => (
                  <tr key={row.id} className={`border-t border-slate-100 ${row.values.active === false ? 'text-slate-400' : ''}`}>
                    {kind === 'partners' && (
                      <td className="px-3 py-2">
                        {row.extra.logo && (
                          <img src={`${API_URL}/api/partners/${row.id}/logo?v=${row.version}`} alt="" className="h-8 w-16 object-contain" />
                        )}
                      </td>
                    )}
                    {COLUMNS[kind].map((c) => (
                      <td key={c} className="max-w-xs truncate px-3 py-2">{shown(t, fields[c], row.values[c])}</td>
                    ))}
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {kind === 'push' && (
                        <>
                          <span className="mr-3 text-xs text-slate-500">{t('settingsAdmin.push.counts', row.extra)}</span>
                          <button className="mr-3 font-medium text-emerald-700 hover:underline" onClick={() => sendNow(row)}>
                            {t('settingsAdmin.push.sendNow')}
                          </button>
                        </>
                      )}
                      <button className="font-medium text-emerald-700 hover:underline" onClick={() => setEditing(row)}>
                        {t('settingsAdmin.edit')}
                      </button>
                      <button className="ml-3 font-medium text-red-600 hover:underline" onClick={() => remove(row)}>
                        {t('settingsAdmin.delete')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Card>
    </div>
  )
}

function shown(t: TFunction, f: Field | undefined, v: Value): ReactNode {
  if (!f || v === null || v === '') {
    return f?.name === 'coins' ? t('settingsAdmin.rule') : t('settingsAdmin.none')
  }
  if (f.type === 'bool') return v ? t('settingsAdmin.on') : t('settingsAdmin.off')
  if (f.type === 'datetime') return when.format(new Date(`${v}:00+05:00`))
  if (f.type === 'ref') return f.options?.find((o) => o.id === v)?.label ?? String(v)
  if (f.type === 'choice') return choiceLabel(t, f.name, String(v))
  if (f.type === 'multiplier') return `×${Number(v).toLocaleString('ru-RU')}`
  return String(v)
}

function choiceLabel(t: TFunction, field: string, v: string): string {
  return field === 'type' ? t(`types.${v}`) : t(`settingsAdmin.choices.${field}.${v}`)
}

// Checked here against the limits the server sent, and again by the server, which has the last word
function check(f: Field, v: Value): Detail | null {
  const blank = v === null || v === ''
  if (f.type === 'bool') return null
  if (blank) return f.required ? { code: 'required', field: f.name } : null
  if (f.type === 'int') {
    const n = Number(v)
    if (!Number.isInteger(n) || (f.min !== null && n < f.min) || (f.max !== null && n > f.max)) {
      return { code: 'out_of_range', field: f.name, min: f.min ?? undefined, max: f.max ?? undefined }
    }
  }
  if (f.type === 'multiplier') {
    // 1,5 and 1.5 both read, as in the Excel file
    const n = Number(String(v).replace(',', '.'))
    if (!Number.isFinite(n) || n < (f.min ?? 1) || n > (f.max ?? 5) || !Number.isInteger(n * 2)) {
      return { code: 'bad_multiplier', field: f.name }
    }
  }
  if ((f.type === 'text' || f.type === 'secret') && f.max !== null) {
    const len = String(v).length
    if (len < (f.min ?? 0) || len > f.max) return { code: 'length', field: f.name, min: f.min ?? 0, max: f.max }
  }
  return null
}

type Values = Record<string, Value>

// The form's schema, from the fields and limits the server sent: each refusal is the message the server would give
function rowSchema(fields: Field[], message: (bad: Detail) => string) {
  return z.object(Object.fromEntries(fields.map((f) => [f.name, z.any().superRefine((v, ctx) => {
    // A blank PIN or password isn't sent: an account keeps its old one
    if (f.type === 'secret' && v === '') return
    const bad = check(f, v as Value)
    if (bad) ctx.addIssue({ code: 'custom', message: message(bad) })
  })])))
}

function RowForm({ kind, token, fields, row, onDone, onCancel, loggedOut }: TabProps & {
  kind: Kind; fields: Field[]; row: Row | null; onDone: () => void; onCancel: () => void
}) {
  const { t } = useTranslation()
  const label = useCallback((f: string) => t(`settingsAdmin.fields.${kind}.${f}`), [t, kind])
  const schema = useMemo(
    () => rowSchema(fields, (bad) => errorText(t, new ApiError(400, bad), label)), [fields, t, label])
  const { control, handleSubmit, setValue } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: Object.fromEntries(fields.map((f) => [f.name, row
      ? (row.values[f.name] ?? (f.type === 'bool' ? false : ''))
      : (f.type === 'bool' ? f.name === 'active' : kind === 'push' && f.name === 'kind' ? 'one_off' : '')])),
  })
  const values = useWatch({ control })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const fail = useFail(loggedOut, setError, label)

  // The first refused field, in the form's order
  function refused(errors: Partial<Record<string, { message?: string }>>) {
    const first = fields.find((f) => errors[f.name])
    setError((first && errors[first.name]?.message) || t('common.error'))
  }

  async function submit(values: Values) {
    setError('')
    const sent = fields.filter((f) => !(f.type === 'secret' && values[f.name] === ''))
    const body: Record<string, Value> = {}
    for (const f of sent) {
      const v = values[f.name]
      body[f.name] = v === '' ? null
        : f.type === 'int' || f.type === 'ref' ? Number(v)
        : f.type === 'multiplier' ? Number(String(v).replace(',', '.')) : v
    }
    setBusy(true)
    try {
      const saved = await confirmed(t, (yes) => {
        const q = yes ? '?confirm=true' : ''
        return row
          ? api(`/api/admin/lists/${kind}/${row.id}${q}`, { token, method: 'PUT', json: { values: body, version: row.version } })
          : api(`/api/admin/lists/${kind}${q}`, { token, json: { values: body } })
      })
      if (saved !== null) onDone()
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <form onSubmit={handleSubmit(submit, refused)} className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-2">
          {fields.map((f) => (
            <label key={f.name} className="flex flex-col gap-1 text-sm">
              <span className="font-medium">{label(f.name)}{f.required && ' *'}</span>
              <FieldInput
                field={f}
                kind={kind}
                value={values[f.name] ?? null}
                disabled={f.fixed && row !== null}
                onChange={(v) => setValue(f.name, v)}
              />
              {f.name === 'coins' && <span className="text-xs text-slate-500">{t('settingsAdmin.rule')}</span>}
              {f.type === 'secret' && row && <span className="text-xs text-slate-500">{t('settingsAdmin.secretHint')}</span>}
              <span className="text-xs text-slate-500">{t(`settingsAdmin.effect.${f.effect}`)}</span>
            </label>
          ))}
        </div>
        {kind === 'partners' && row && <LogoUpload token={token} partner={row} onDone={onDone} loggedOut={loggedOut} />}
        {kind === 'badges' && <p className="text-xs text-slate-500">{t('settingsAdmin.badgeHint')}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-3">
          <Button disabled={busy}>{t('settingsAdmin.save')}</Button>
          <Button type="button" variant="outline" onClick={onCancel}>{t('settingsAdmin.cancel')}</Button>
        </div>
      </form>
    </Card>
  )
}

function FieldInput({ field: f, kind, value, disabled, onChange }:
  { field: Field; kind: Kind; value: Value; disabled: boolean; onChange: (v: Value) => void }) {
  const { t } = useTranslation()
  const select = 'h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-base'
  if (f.type === 'bool') {
    return <input type="checkbox" className="size-5" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
  }
  if (f.type === 'choice') {
    return (
      <select className={select} value={String(value ?? '')} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {!f.choices.includes('') && <option value="" />}
        {f.choices.map((c) => <option key={c} value={c}>{choiceLabel(t, f.name, c)}</option>)}
      </select>
    )
  }
  if (f.type === 'ref') {
    return (
      <select className={select} value={value === null ? '' : String(value)} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('settingsAdmin.none')}</option>
        {(f.options ?? []).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
    )
  }
  if (f.type === 'text' && (f.max ?? 0) > 300 && kind !== 'stages') {
    return (
      <textarea
        className="min-h-24 w-full rounded-xl border border-slate-300 bg-white px-4 py-2 text-base"
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
      />
    )
  }
  if (f.type === 'multiplier') {
    return <Input type="text" inputMode="decimal" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
  }
  return (
    <Input
      type={f.type === 'int' ? 'number' : f.type === 'datetime' ? 'datetime-local' : f.type === 'secret' ? 'password' : 'text'}
      min={f.type === 'int' ? f.min ?? undefined : undefined}
      max={f.type === 'int' ? f.max ?? undefined : undefined}
      autoComplete={f.type === 'secret' ? 'new-password' : undefined}
      value={String(value ?? '')}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function LogoUpload({ token, partner, onDone, loggedOut }: TabProps & { partner: Row; onDone: () => void }) {
  const { t } = useTranslation()
  const [error, setError] = useState('')
  const label = useCallback((f: string) => f, [])
  const fail = useFail(loggedOut, setError, label)

  async function upload(file: File | undefined) {
    if (!file) return
    setError('')
    const form = new FormData()
    form.append('file', file)
    try {
      await api(`/api/admin/partners/${partner.id}/logo`, { token, form })
      onDone()
    } catch (err) {
      fail(err)
    }
  }

  return (
    <div className="flex flex-col gap-1 text-sm">
      <label className="flex cursor-pointer items-center gap-3">
        <span className="rounded-lg bg-slate-100 px-3 py-2 font-medium hover:bg-slate-200">{t('settingsAdmin.logoUpload')}</span>
        <input type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
      </label>
      {error && <p className="text-red-600">{error}</p>}
    </div>
  )
}

function Settings({ token, loggedOut, dateLocked }: TabProps & { dateLocked: boolean }) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<Setting[] | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const label = useCallback((f: string) => t(`settingsAdmin.fields.settings.${f}`), [t])
  const fail = useFail(loggedOut, setError, label)

  const load = useCallback(() => {
    api<Setting[]>('/api/admin/settings', { token }).then((all) => {
      const r = all.filter((s) => !isPush(s.key))
      setRows(r)
      setDrafts(Object.fromEntries(r.map((s) => [s.key, draft(s)])))
    }).catch(fail)
  }, [token, fail])

  useEffect(load, [load])

  async function save(s: Setting) {
    setError('')
    setSaved('')
    // A text setting here is a date (YYYY-MM-DD) or blank, or the skin's id; the server checks it
    let value: string | number = drafts[s.key] ?? ''
    if (s.text === null) {
      const n = Number(value.replace(',', '.'))
      if (value === '' || Number.isNaN(n) || n < s.min || n > s.max || (s.integer && !Number.isInteger(n))) {
        setError(t('settingsAdmin.errors.out_of_range', { field: label(s.key), min: s.min, max: s.max }))
        return
      }
      value = n
    }
    try {
      const done = await confirmed(t, (yes) => api(`/api/admin/settings/${s.key}${yes ? '?confirm=true' : ''}`, {
        token, method: 'PUT', json: { value, version: s.version },
      }))
      if (done !== null) {
        setSaved(s.key)
        load()
      }
    } catch (err) {
      fail(err)
    }
  }

  if (!rows) return <p className="text-slate-500">{t('common.loading')}</p>
  return (
    <Card className="flex flex-col gap-4">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {rows.map((s) => {
        // From the banner on, the photo deletion date stays as announced
        const locked = dateLocked && s.key === 'photo_delete_date'
        return (
        <div key={s.key} className="flex flex-col gap-1 border-b border-slate-100 pb-4 last:border-0 last:pb-0">
          <span className="text-sm font-medium">{label(s.key)}</span>
          {s.choices && (
            <SkinChoice
              name={s.key}
              choices={s.choices as Skin[]}
              value={drafts[s.key] ?? ''}
              onChange={(v) => setDrafts((d) => ({ ...d, [s.key]: v }))}
            />
          )}
          <div className="flex items-center gap-3">
            {!s.choices && <Input
              type={s.text === null ? 'number' : 'date'}
              className="max-w-40"
              min={s.text === null ? s.min : undefined}
              max={s.text === null ? s.max : undefined}
              step={s.integer ? 1 : 0.1}
              value={drafts[s.key] ?? ''}
              onChange={(e) => setDrafts((d) => ({ ...d, [s.key]: e.target.value }))}
              disabled={locked}
            />}
            <Button variant="outline" onClick={() => save(s)} disabled={locked || drafts[s.key] === draft(s)}>
              {t('settingsAdmin.save')}
            </Button>
            {saved === s.key && <span className="text-sm text-emerald-700">{t('settingsAdmin.saved')}</span>}
          </div>
          <span className="text-xs text-slate-500">
            {locked
              ? t('settingsAdmin.errors.photo_date_locked')
              : s.choices
                ? t(`settingsAdmin.effect.${s.effect}`)
                : s.text === null
                  ? `${s.min}–${s.max} · ${t(`settingsAdmin.effect.${s.effect}`)}`
                  : `${t('settingsAdmin.dateBlank')} · ${t(`settingsAdmin.effect.${s.effect}`)}`}
          </span>
        </div>
        )
      })}
    </Card>
  )
}

// The «Push» tab's own settings: the switch, then each kind's text. The schedule below is the push list
function PushSettings({ token, loggedOut }: TabProps) {
  const { t } = useTranslation()
  const [rows, setRows] = useState<Setting[] | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const label = useCallback((f: string) => t(`settingsAdmin.fields.settings.${f}`), [t])
  const fail = useFail(loggedOut, setError, label)

  const load = useCallback(() => {
    api<Setting[]>('/api/admin/settings', { token }).then((all) => {
      const r = all.filter((s) => isPush(s.key))
      setRows(r)
      setDrafts(Object.fromEntries(r.filter((s) => s.text !== null).map((s) => [s.key, s.text ?? ''])))
    }).catch(fail)
  }, [token, fail])

  useEffect(load, [load])

  async function save(s: Setting, value: string | number) {
    setError('')
    setSaved('')
    try {
      await api(`/api/admin/settings/${s.key}`, { token, method: 'PUT', json: { value, version: s.version } })
      setSaved(s.key)
      load()
    } catch (err) {
      fail(err)
    }
  }

  if (!rows) return <p className="text-slate-500">{t('common.loading')}</p>
  const enabled = rows.find((s) => s.key === 'push_enabled')
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {enabled && (
          <label className="flex items-center gap-3 text-sm font-medium">
            <input type="checkbox" className="size-5" checked={enabled.value === 1} onChange={(e) => save(enabled, e.target.checked ? 1 : 0)} />
            {t('settingsAdmin.push.switch')}
            <span className="text-xs font-normal text-slate-500">{t('settingsAdmin.push.switchHint')}</span>
          </label>
        )}
        <span className="text-sm font-semibold">{t('settingsAdmin.push.texts')}</span>
        {rows.filter((s) => s.text !== null).map((s) => (
          <div key={s.key} className="flex flex-col gap-1">
            <span className="text-sm font-medium">{label(s.key)}</span>
            <div className="flex items-center gap-3">
              <Input
                maxLength={s.max}
                value={drafts[s.key] ?? ''}
                onChange={(e) => setDrafts((d) => ({ ...d, [s.key]: e.target.value }))}
              />
              <Button variant="outline" onClick={() => save(s, drafts[s.key] ?? '')} disabled={drafts[s.key] === s.text}>
                {t('settingsAdmin.save')}
              </Button>
              {saved === s.key && <span className="text-sm text-emerald-700">{t('settingsAdmin.saved')}</span>}
            </div>
            <span className="text-xs text-slate-500">{t(`settingsAdmin.effect.${s.effect}`)}</span>
          </div>
        ))}
      </Card>
      <h2 className="text-base font-semibold">{t('settingsAdmin.push.schedule')}</h2>
      <ListTab kind="push" token={token} loggedOut={loggedOut} />
    </div>
  )
}

// The event's skin, one per event: each choice shows the same card in that skin's guest theme, in its own faces
function SkinChoice({ name, choices, value, onChange }:
  { name: string; choices: Skin[]; value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {choices.map((skin) => (
        <label
          key={skin}
          className={`flex cursor-pointer flex-col gap-2 rounded-lg p-2 ring-2 ${value === skin ? 'ring-emerald-600' : 'ring-slate-200'}`}
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            <input type="radio" name={name} value={skin} checked={value === skin} onChange={() => onChange(skin)} />
            {t(`settingsAdmin.choices.${name}.${skin}`)}
          </span>
          <SkinPreview skin={skin} />
        </label>
      ))}
    </div>
  )
}

function SkinPreview({ skin }: { skin: Skin }) {
  const { t } = useTranslation()
  usePreviewFonts(skin)
  return (
    <div data-theme={THEMES[skin].dark} className="gc-root gc-ribs flex flex-col gap-3 p-3" aria-hidden>
      <ConsoleCard>
        <span className="gc-display-m">{t(`settingsAdmin.choices.skin.${skin}`)}</span>
        <Stripe />
        <span className="gc-button gc-button--primary gc-button--md gc-label">
          <span className="gc-button__text">{t('task.do')}</span>
        </span>
      </ConsoleCard>
      <div className="gc-wood h-3" />
    </div>
  )
}

const LOG_KINDS = ['stages', 'tasks', 'prizes', 'questions', 'levels', 'partners', 'staff', 'settings', 'rating', 'guests', 'push', 'badges']

function Log({ token, loggedOut }: TabProps) {
  const { t } = useTranslation()
  const [events, setEvents] = useState<Event[] | null>(null)
  const [admins, setAdmins] = useState<{ id: number; name: string }[]>([])
  const [filter, setFilter] = useState({ kind: '', item: '', staff_id: '', date_from: '', date_to: '' })
  const [error, setError] = useState('')
  const label = useCallback((f: string) => f, [])
  const fail = useFail(loggedOut, setError, label)

  const query = new URLSearchParams(Object.entries(filter).filter(([, v]) => v)).toString()
  const load = useCallback((q: string) => {
    api<Event[]>(`/api/admin/log${q ? `?${q}` : ''}`, { token }).then(setEvents).catch(fail)
  }, [token, fail])

  useEffect(() => {
    load('')
    api<List>('/api/admin/lists/staff', { token })
      .then((l) => setAdmins(l.rows.filter((r) => r.values.role === 'admin').map((r) => ({ id: r.id, name: String(r.values.name) }))))
      .catch(fail)
  }, [load, token, fail])

  function fieldName(e: Event): string {
    if (e.field === '_created') return t('settingsAdmin.log.created')
    if (e.field === '_deleted') return t('settingsAdmin.log.deleted')
    if (e.kind === 'settings') return t(`settingsAdmin.fields.settings.${e.item}`, { defaultValue: e.field })
    return t(`settingsAdmin.fields.${e.kind}.${e.field}`, {
      defaultValue: t(`settingsAdmin.log.extraFields.${e.field}`, { defaultValue: e.field }),
    })
  }

  // A skin change reads «Консоль → Стимпанк», not its ids
  function logValue(e: Event, v: string | null): string {
    if (v === null) return ''
    return e.kind === 'settings' && e.item === 'skin' ? t(`settingsAdmin.choices.skin.${v}`, { defaultValue: v }) : v
  }

  const set = (k: keyof typeof filter) => (v: string) => setFilter((f) => ({ ...f, [k]: v }))
  const select = 'h-12 rounded-xl border border-slate-300 bg-white px-3 text-base'
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('settingsAdmin.log.kind')}
          <select className={select} value={filter.kind} onChange={(e) => set('kind')(e.target.value)}>
            <option value="">{t('settingsAdmin.log.all')}</option>
            {LOG_KINDS.map((k) => <option key={k} value={k}>{t(`settingsAdmin.log.kinds.${k}`)}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('settingsAdmin.log.item')}
          <Input className="w-40" value={filter.item} onChange={(e) => set('item')(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('settingsAdmin.log.admin')}
          <select className={select} value={filter.staff_id} onChange={(e) => set('staff_id')(e.target.value)}>
            <option value="">{t('settingsAdmin.log.all')}</option>
            {admins.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('settingsAdmin.log.from')}
          <Input type="date" value={filter.date_from} onChange={(e) => set('date_from')(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('settingsAdmin.log.to')}
          <Input type="date" value={filter.date_to} onChange={(e) => set('date_to')(e.target.value)} />
        </label>
        <Button onClick={() => load(query)}>{t('settingsAdmin.log.filter')}</Button>
        <Button
          variant="outline"
          onClick={() => download(`/api/admin/log/export${query ? `?${query}` : ''}`, token, 'change-log.xlsx').catch(fail)}
        >
          {t('settingsAdmin.log.export')}
        </Button>
      </Card>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {events && (
        <Card className="overflow-x-auto p-0">
          {events.length === 0
            ? <p className="p-6 text-sm text-slate-500">{t('settingsAdmin.empty')}</p>
            : (
              <table className="w-full text-left text-sm">
                <thead className="text-slate-500">
                  <tr>
                    {['time', 'admin', 'kind', 'item', 'field', 'old', 'new', 'source'].map((h) => (
                      <th key={h} className="px-3 py-2 font-medium">{t(`settingsAdmin.log.${h}`)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id} className="border-t border-slate-100">
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums">{when.format(new Date(e.created_at))}</td>
                      <td className="px-3 py-2">{e.staff_name}</td>
                      <td className="px-3 py-2">{t(`settingsAdmin.log.kinds.${e.kind}`, { defaultValue: e.kind })}</td>
                      <td className="max-w-xs truncate px-3 py-2">{e.item}</td>
                      <td className="px-3 py-2">{fieldName(e)}</td>
                      <td className="max-w-xs truncate px-3 py-2 text-slate-500">{logValue(e, e.old_value)}</td>
                      <td className="max-w-xs truncate px-3 py-2">{logValue(e, e.new_value)}</td>
                      <td className="px-3 py-2">{t(`settingsAdmin.log.sources.${e.source}`)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Card>
      )}
    </div>
  )
}
