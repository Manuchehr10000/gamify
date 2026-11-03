import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card, Screen } from '../components/ui'

type Result = {
  added: number
  changed: number
  // Any bad row refuses the whole list
  failed: { row: number; reason: string }[]
  // The preview: whom the list adds and changes; nobody is ever hidden
  items: { reg_id: string; name: string; change: 'added' | 'changed' }[]
}

export function AdminGuests() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('admin'))
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Result | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function fail(err: unknown) {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('admin')
      setToken(null)
      return
    }
    const detail = err instanceof ApiError ? err.detail as { code?: string; columns?: string[] } : null
    if (detail?.code === 'missing_columns') {
      const columns = (detail.columns ?? []).map((c) => t(`admin.columns.${c}`)).join(', ')
      setError(t('admin.missingColumns', { columns }))
    } else {
      setError(t('common.error'))
    }
  }

  // First the preview; «Применить» sends the same file again to apply it
  async function send(path: string, then: (r: Result) => void) {
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    const form = new FormData()
    form.append('file', file)
    try {
      then(await api<Result>(path, { token, form }))
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  function check(e: FormEvent) {
    e.preventDefault()
    setPreview(null)
    send('/api/admin/guests/import/preview', setPreview)
  }

  function apply() {
    send('/api/admin/guests/import', (r) => {
      if (r.failed.length) {
        setPreview(r)
      } else {
        setResult(r)
        setPreview(null)
      }
    })
  }

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  return (
    <Screen>
      <h1 className="text-xl font-semibold">{t('staff.adminTitle')}</h1>
      <Card>
        <form onSubmit={check} className="flex flex-col gap-4">
          <p className="text-sm text-slate-600">{t('admin.uploadHint')}</p>
          <label className="flex cursor-pointer items-center gap-3 text-sm">
            <span className="rounded-lg bg-slate-100 px-3 py-2 font-medium hover:bg-slate-200">{t('admin.chooseFile')}</span>
            <span className="truncate text-slate-600">{file?.name ?? t('admin.noFile')}</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="sr-only"
            />
          </label>
          <Button disabled={!file || busy}>{t('admin.upload')}</Button>
        </form>
      </Card>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {preview && preview.failed.length > 0 && (
        <Card className="flex flex-col gap-2">
          <p className="font-medium text-red-700">{t('admin.failedTitle')}</p>
          <ul className="text-sm text-red-700">
            {preview.failed.map((f) => (
              <li key={f.row}>{t('admin.row', { row: f.row, reason: t(`admin.reasons.${f.reason}`) })}</li>
            ))}
          </ul>
        </Card>
      )}
      {preview && preview.failed.length === 0 && (
        <Card className="flex flex-col gap-3">
          <p className="font-medium">{t('admin.preview.title')}</p>
          {preview.items.length === 0
            ? <p className="text-sm text-slate-600">{t('admin.preview.none')}</p>
            : (
              <ul className="max-h-80 overflow-y-auto text-sm text-slate-700">
                {preview.items.map((i) => (
                  <li key={i.reg_id}>
                    {t('admin.preview.item', { reg_id: i.reg_id, name: i.name, change: t(`admin.preview.change.${i.change}`) })}
                  </li>
                ))}
              </ul>
            )}
          <p className="text-sm text-slate-500">{t('admin.preview.note')}</p>
          <div className="flex gap-3">
            <Button disabled={busy || preview.items.length === 0} onClick={apply}>{t('admin.preview.apply')}</Button>
            <Button variant="outline" disabled={busy} onClick={() => setPreview(null)}>{t('admin.preview.cancel')}</Button>
          </div>
        </Card>
      )}
      {result && (
        <Card className="flex flex-col gap-2">
          <p className="font-medium">{t('admin.added', { count: result.added })}</p>
          {result.changed > 0 && <p className="text-slate-600">{t('admin.changed', { count: result.changed })}</p>}
        </Card>
      )}
      <Button variant="outline" onClick={() => download('/api/admin/guests/export', token, 'guests.csv').catch(fail)}>
        {t('admin.download')}
      </Button>
    </Screen>
  )
}
