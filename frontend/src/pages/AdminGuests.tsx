import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { AdminShell, DataTable, FileUpload } from '../components/console/admin'
import { Button, Callout, Card } from '../components/console/ui'

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
    <AdminShell
      title={t('staff.adminTitle')}
      actions={(
        <Button variant="outline" icon="download" block={false} onClick={() => download('/api/admin/guests/export', token, 'guests.csv').catch(fail)}>
          {t('admin.download')}
        </Button>
      )}
    >
      <Card>
        <form onSubmit={check} className="gc-admin-form" aria-busy={busy || undefined}>
          <p className="gc-admin-note gc-body-s">{t('admin.uploadHint')}</p>
          <FileUpload accept=".csv,text/csv" fileName={file?.name} busy={busy} onChange={setFile} />
          <Button type="submit" busy={busy} disabled={!file}>{t('admin.upload')}</Button>
        </form>
      </Card>
      {/* A file with missing columns: today's message */}
      {error && <Callout tone="danger">{error}</Callout>}
      {preview && preview.failed.length > 0 && (
        <>
          <Callout tone="danger">{t('admin.failedTitle')}</Callout>
          <Card>
            <DataTable
              caption={t('admin.failedRows')}
              columns={[{ key: 'row', label: t('admin.rowNumber'), align: 'right' }, { key: 'reason', label: t('admin.reason') }]}
              rows={preview.failed.map((f) => ({ id: f.row, row: f.row, reason: t(`admin.reasons.${f.reason}`) }))}
            />
          </Card>
        </>
      )}
      {preview && preview.failed.length === 0 && (
        <Card>
          <p className="gc-label">{t('admin.preview.title')}</p>
          {preview.items.length === 0
            ? <p className="gc-admin-note gc-body-s">{t('admin.preview.none')}</p>
            : (
              <ul className="gc-list-group gc-admin-preview gc-body-s">
                {preview.items.map((i) => (
                  <li key={i.reg_id}>
                    {t('admin.preview.item', { reg_id: i.reg_id, name: i.name, change: t(`admin.preview.change.${i.change}`) })}
                  </li>
                ))}
              </ul>
            )}
          <p className="gc-admin-note gc-body-s">{t('admin.preview.note')}</p>
          <div className="gc-admin-pair">
            <Button variant="outline" disabled={busy} onClick={() => setPreview(null)}>{t('admin.preview.cancel')}</Button>
            <Button busy={busy} disabled={preview.items.length === 0} onClick={apply}>{t('admin.preview.apply')}</Button>
          </div>
        </Card>
      )}
      {result && (
        <Callout tone="success">
          <p>{t('admin.added', { count: result.added })}</p>
          {result.changed > 0 && <p>{t('admin.changed', { count: result.changed })}</p>}
        </Callout>
      )}
    </AdminShell>
  )
}
