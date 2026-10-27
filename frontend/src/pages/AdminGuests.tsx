import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card, Screen } from '../components/ui'

type Result = { added: number; updated: number; failed: { row: number; reason: string }[] }

export function AdminGuests() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('admin'))
  const [file, setFile] = useState<File | null>(null)
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

  async function upload(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    const form = new FormData()
    form.append('file', file)
    try {
      setResult(await api<Result>('/api/admin/guests/import', { token, form }))
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  return (
    <Screen>
      <h1 className="text-xl font-semibold">{t('staff.adminTitle')}</h1>
      <Card>
        <form onSubmit={upload} className="flex flex-col gap-4">
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
      {result && (
        <Card className="flex flex-col gap-2">
          <p className="font-medium">{t('admin.added', { count: result.added })}</p>
          {result.updated > 0 && <p className="text-slate-600">{t('admin.updated', { count: result.updated })}</p>}
          {result.failed.length > 0 && (
            <>
              <p className="mt-2 font-medium text-red-700">{t('admin.failedTitle')}</p>
              <ul className="text-sm text-red-700">
                {result.failed.map((f) => (
                  <li key={f.row}>{t('admin.row', { row: f.row, reason: t(`admin.reasons.${f.reason}`) })}</li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}
      <Button variant="outline" onClick={() => download('/api/admin/guests/export', token, 'guests.csv').catch(fail)}>
        {t('admin.download')}
      </Button>
    </Screen>
  )
}
