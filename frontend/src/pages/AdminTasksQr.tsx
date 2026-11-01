import { Printer } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button } from '../components/ui'

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
    <main className="min-h-dvh bg-white px-4 py-8 text-slate-900">
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
          <div>
            <h1 className="text-xl font-semibold">{t('qrSheet.title')}</h1>
            <p className="text-sm text-slate-600">{t('qrSheet.hint', { site: window.location.host })}</p>
          </div>
          <div className="flex gap-2">
            <Link to="/admin/tasks" className="inline-flex h-12 items-center rounded-xl border border-slate-300 px-5 font-medium">
              {t('common.back')}
            </Link>
            <Button onClick={() => window.print()} disabled={!tasks?.length}>
              <Printer className="mr-2 size-5" aria-hidden />
              {t('qrSheet.print')}
            </Button>
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {tasks && tasks.length === 0 && <p className="text-slate-600">{t('qrSheet.none')}</p>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 print:grid-cols-2">
          {tasks?.map((task) => (
            <div key={task.code} className="flex break-inside-avoid flex-col items-center gap-3 rounded-2xl border-2 border-slate-300 p-6 text-center">
              <QRCodeSVG value={`${window.location.origin}/q/${task.qr_code}`} size={220} marginSize={2} />
              <p className="text-lg font-semibold">{task.text}</p>
              <p className="text-sm text-slate-500">{t('qrSheet.meta', { code: task.code, stage: task.stage })}</p>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
