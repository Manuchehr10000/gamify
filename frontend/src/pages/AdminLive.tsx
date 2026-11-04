import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, api, download, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { AdminShell, DataTable } from '../components/console/admin'
import { SectionHeading } from '../components/console/rewards'
import { HallSwitch, StatTile } from '../components/console/staff'
import { Button, Callout, Card, Loading } from '../components/console/ui'

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
  // Pushes: active subscriptions, accepted by the push service, reported arrived by phones, refused or gone
  push_opt_ins: number
  push_sends: number
  push_deliveries: number
  push_failures: number
}

// A guest whose stored totals differ from the sum of their score events
type Mismatch = { name: string; points: number; points_sum: number; coins: number; coins_sum: number }
// The partner picker reads the settings list of partners
type PartnerRow = { id: number; values: { name: string } }

const POLL_MS = 30_000

// The organizer's live numbers during the forum: current counts only, refreshed every 30 seconds
export function AdminLive() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('admin'))
  const [live, setLive] = useState<Live | null>(null)
  const [error, setError] = useState(false)
  const [mismatches, setMismatches] = useState<Mismatch[] | null>(null)
  const [checking, setChecking] = useState(false)
  const [partners, setPartners] = useState<PartnerRow[]>([])
  const [picked, setPicked] = useState('')

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

  useEffect(() => {
    if (!token) return
    api<{ rows: PartnerRow[] }>('/api/admin/lists/partners', { token }).then((l) => setPartners(l.rows)).catch(fail)
  }, [token, fail])

  if (!token) return <StaffLogin role="admin" onLogin={setToken} />

  // One partner's Excel file: totals, hours and photo links
  function partnerReport() {
    const p = partners.find((r) => String(r.id) === picked)
    if (!p || !token) return
    download(`/api/admin/partners/${p.id}/report`, token, `${p.values.name}.xlsx`).catch(fail)
  }

  function checkBalance() {
    setChecking(true)
    api<Mismatch[]>('/api/admin/balance-check', { token })
      .then(setMismatches)
      .catch(fail)
      .finally(() => setChecking(false))
  }

  const oldest = live?.oldest_seconds
  const completions = { key: 'n', label: t('live.completions'), align: 'right' as const }
  return (
    <AdminShell
      title={t('live.title')}
      actions={(
        <>
          <Button variant="outline" icon="download" block={false} onClick={() => download('/api/admin/partners/export', token, 'partners.csv').catch(fail)}>
            {t('live.report')}
          </Button>
          <select
            className="gc-text-input__field"
            style={{ width: 'auto', maxWidth: '100%' }}
            aria-label={t('live.partnerReport')}
            value={picked}
            onChange={(e) => setPicked(e.target.value)}
          >
            <option value="">{t('live.pickPartner')}</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.values.name}</option>)}
          </select>
          <Button variant="outline" icon="download" block={false} disabled={!picked} onClick={partnerReport}>
            {t('live.partnerReport')}
          </Button>
        </>
      )}
    >
      <Card>
        <HallSwitch token={token} onLoggedOut={() => fail(new ApiError(401, null))} />
      </Card>
      {error && <Callout tone="danger">{t('common.error')}</Callout>}
      {!live && !error && <Loading />}
      {live && (
        <>
          {/* Seven readouts; the oldest wait in whole minutes, with no warning colour at any age */}
          <div className="gc-admin-stats">
            <StatTile label={t('live.loggedIn')} value={live.logged_in} />
            <StatTile label={t('live.active')} value={live.active} />
            <StatTile label={t('live.waiting')} value={live.waiting} />
            <StatTile label={t('live.oldest')} value={oldest == null ? '—' : t('live.minutes', { count: Math.floor(oldest / 60) })} />
            <StatTile label={t('live.bought')} value={live.bought} />
            <StatTile label={t('live.issued')} value={live.issued} />
            <StatTile label={t('live.left')} value={live.left} />
          </div>
          <Card>
            <SectionHeading>{t('live.push')}</SectionHeading>
            <div className="gc-admin-stats">
              <StatTile label={t('live.pushOptIns')} value={live.push_opt_ins} />
              <StatTile label={t('live.pushSends')} value={live.push_sends} />
              <StatTile label={t('live.pushDeliveries')} value={live.push_deliveries} />
              <StatTile label={t('live.pushFailures')} value={live.push_failures} />
            </div>
          </Card>
          <Card>
            <SectionHeading>{t('live.byType')}</SectionHeading>
            <DataTable
              columns={[{ key: 'type', label: t('live.type') }, completions]}
              rows={live.by_type.map((r) => ({ id: r.name, type: t(`types.${r.name}`), n: r.completions }))}
              empty={t('live.none')}
            />
          </Card>
          <Card>
            <SectionHeading>{t('live.byStage')}</SectionHeading>
            <DataTable
              columns={[{ key: 'stage', label: t('live.stage') }, completions]}
              rows={live.by_stage.map((s) => ({ id: s.number, stage: `${s.number}. ${s.name}`, n: s.completions }))}
              empty={t('live.none')}
            />
          </Card>
          <Card>
            <SectionHeading>{t('live.partners')}</SectionHeading>
            <DataTable
              columns={[{ key: 'partner', label: t('live.partner') }, completions, { key: 'g', label: t('live.guests'), align: 'right' }]}
              rows={live.partners.map((p) => ({ id: p.partner, partner: p.partner, n: p.completions, g: p.guests }))}
              empty={t('live.none')}
            />
          </Card>
        </>
      )}
      <Card>
        <p className="gc-admin-note gc-body-s">{t('live.balanceHint')}</p>
        <Button variant="outline" busy={checking} onClick={checkBalance}>{t('live.balance')}</Button>
        {mismatches && (
          <DataTable
            columns={[
              { key: 'name', label: t('live.guest') },
              { key: 'points', label: t('live.points'), align: 'right' },
              { key: 'pointsSum', label: t('live.pointsSum'), align: 'right' },
              { key: 'coins', label: t('live.coins'), align: 'right' },
              { key: 'coinsSum', label: t('live.coinsSum'), align: 'right' },
            ]}
            rows={mismatches.map((m, i) => ({ id: i, name: m.name, points: m.points, pointsSum: m.points_sum, coins: m.coins, coinsSum: m.coins_sum }))}
            empty={t('live.balanceOk')}
          />
        )}
      </Card>
    </AdminShell>
  )
}
