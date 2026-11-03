import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, api, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card } from '../components/ui'

type Live = {
  logged_in: number
  active: number
  by_type: { name: string; completions: number }[]
  by_stage: { number: number; name: string; completions: number }[]
  partners: { partner: string; completions: number; guests: number }[]
  waiting: number
  oldest_seconds: number | null
  bought: number
  issued: number
  left: number
}

// A guest whose stored totals differ from the sum of their score events
type Mismatch = { name: string; points: number; points_sum: number; coins: number; coins_sum: number }

const POLL_MS = 30_000

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-3xl font-semibold tabular-nums">{value}</span>
      <span className="text-sm text-slate-600">{label}</span>
    </div>
  )
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-slate-500">
        <tr>
          {head.map((h, i) => (
            <th key={h} className={`py-1 font-medium ${i ? 'pl-2 text-right' : ''}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={String(r[0])} className="border-t border-slate-100">
            {r.map((c, i) => (
              <td key={i} className={`py-2 ${i ? 'pl-2 text-right tabular-nums' : 'font-medium'}`}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// The organizer's live numbers during the forum: current counts only, refreshed every 30 seconds
export function AdminLive() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('admin'))
  const [live, setLive] = useState<Live | null>(null)
  const [error, setError] = useState(false)
  const [mismatches, setMismatches] = useState<Mismatch[] | null>(null)
  const [checking, setChecking] = useState(false)

  const fail = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('admin')
      setToken(null)
    } else {
      setError(true)
    }
  }, [])

  useEffect(() => {
    if (!token) return
    let alive = true
    const load = () =>
      api<Live>('/api/admin/live', { token })
        .then((data) => {
          if (!alive) return
          setLive(data)
          setError(false)
        })
        .catch((err) => alive && fail(err))
    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [token, fail])

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  function checkBalance() {
    setChecking(true)
    api<Mismatch[]>('/api/admin/balance-check', { token })
      .then(setMismatches)
      .catch(fail)
      .finally(() => setChecking(false))
  }

  const oldest = live?.oldest_seconds
  return (
    <main className="min-h-dvh bg-slate-50 px-4 py-8 text-slate-900">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        <h1 className="text-xl font-semibold">{t('live.title')}</h1>
        {error && <p className="text-sm text-red-600">{t('common.error')}</p>}
        {live && (
          <>
            <Card className="grid grid-cols-2 gap-6">
              <Stat label={t('live.loggedIn')} value={live.logged_in} />
              <Stat label={t('live.active')} value={live.active} />
            </Card>
            <Card className="flex flex-col gap-3">
              <h2 className="font-semibold">{t('live.moderation')}</h2>
              <div className="grid grid-cols-2 gap-6">
                <Stat label={t('live.waiting')} value={live.waiting} />
                <Stat
                  label={t('live.oldest')}
                  value={oldest == null ? '—' : t('live.minutes', { count: Math.floor(oldest / 60) })}
                />
              </div>
            </Card>
            <Card className="flex flex-col gap-3">
              <h2 className="font-semibold">{t('live.market')}</h2>
              <div className="grid grid-cols-3 gap-6">
                <Stat label={t('live.bought')} value={live.bought} />
                <Stat label={t('live.issued')} value={live.issued} />
                <Stat label={t('live.left')} value={live.left} />
              </div>
            </Card>
            <Card className="flex flex-col gap-3">
              <h2 className="font-semibold">{t('live.byType')}</h2>
              {live.by_type.length === 0
                ? <p className="text-sm text-slate-500">{t('live.none')}</p>
                : <Table head={[t('live.type'), t('live.completions')]}
                    rows={live.by_type.map((r) => [t(`types.${r.name}`), r.completions])} />}
            </Card>
            <Card className="flex flex-col gap-3">
              <h2 className="font-semibold">{t('live.byStage')}</h2>
              {live.by_stage.length === 0
                ? <p className="text-sm text-slate-500">{t('live.none')}</p>
                : <Table head={[t('live.stage'), t('live.completions')]}
                    rows={live.by_stage.map((s) => [`${s.number}. ${s.name}`, s.completions])} />}
            </Card>
            <Card className="flex flex-col gap-3">
              <h2 className="font-semibold">{t('live.partners')}</h2>
              {live.partners.length === 0
                ? <p className="text-sm text-slate-500">{t('live.none')}</p>
                : <Table head={[t('live.partner'), t('live.completions'), t('live.guests')]}
                    rows={live.partners.map((p) => [p.partner, p.completions, p.guests])} />}
            </Card>
          </>
        )}
        <Button variant="outline" onClick={() => download('/api/admin/partners/export', token, 'partners.csv').catch(fail)}>
          {t('live.report')}
        </Button>
        <Card className="flex flex-col gap-3">
          <p className="text-sm text-slate-600">{t('live.balanceHint')}</p>
          <Button variant="outline" disabled={checking} onClick={checkBalance}>{t('live.balance')}</Button>
          {mismatches && (mismatches.length === 0
            ? <p className="text-sm text-slate-500">{t('live.balanceOk')}</p>
            : <Table head={[t('live.guest'), t('live.points'), t('live.pointsSum'), t('live.coins'), t('live.coinsSum')]}
                rows={mismatches.map((m) => [m.name, m.points, m.points_sum, m.coins, m.coins_sum])} />)}
        </Card>
      </div>
    </main>
  )
}
