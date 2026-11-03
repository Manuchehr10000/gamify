import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { AdminShell } from '../components/console/admin'
import { QrCard } from '../components/console/staff'
import { Button, Callout, Loading, MessageCard } from '../components/console/ui'

type QrTask = { code: string; stage: number; text: string; qr_code: string }

// One sheet to print and cut: each QR opens <this site>/q/<code>, so codes printed from dev work only on dev
export function AdminTasksQr() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('admin'))
  const [tasks, setTasks] = useState<QrTask[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    api<QrTask[]>('/api/admin/tasks/qr', { token })
      .then(setTasks)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          tokens.clear('admin')
          setToken(null)
        } else {
          setError(t('common.error'))
        }
      })
  }, [token, t])

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  return (
    <AdminShell
      title={t('qrSheet.title')}
      actions={(
        <Button icon="printer" block={false} onClick={() => window.print()} disabled={!tasks?.length}>{t('qrSheet.print')}</Button>
      )}
    >
      <p className="gc-admin-note gc-body-s gc-no-print">{t('qrSheet.hint', { site: window.location.host })}</p>
      {/* Printing leaves only the QR cards */}
      {error && <div className="gc-no-print"><Callout tone="danger">{error}</Callout></div>}
      {!tasks && !error && <div className="gc-no-print"><Loading /></div>}
      {tasks && tasks.length === 0 && <MessageCard icon="qr" title={t('qrSheet.none')} />}
      {tasks && tasks.length > 0 && (
        <ul className="gc-qr-sheet">
          {tasks.map((task) => (
            <li key={task.code}>
              <QrCard title={task.text} caption={t('qrSheet.meta', { code: task.code, stage: task.stage })}>
                <QRCodeSVG value={`${window.location.origin}/q/${task.qr_code}`} size={220} marginSize={2} />
              </QrCard>
            </li>
          ))}
        </ul>
      )}
    </AdminShell>
  )
}
