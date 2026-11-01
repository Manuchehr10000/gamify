import { Check, ChevronLeft, Coins, Lock } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { Button, Card, Screen } from '../components/ui'
import { hhmm } from '../feed'
import { PartnerBadge } from './Feed'

type Prize = {
  id: number
  name: string
  partner: string
  price: number
  left: number
  code: string | null
  issued_at: string | null
}
type MarketData = { coins: number; open: boolean; opens_at: string | null; prizes: Prize[] }

// Ask again often enough that «Получено» shows soon after the stand taps «Выдано»
const POLL_MS = 10_000

type State = { kind: 'loading' } | { kind: 'loggedOut' } | { kind: 'error' } | { kind: 'ready'; market: MarketData }

export function Market() {
  const { t } = useTranslation()
  const [state, setState] = useState<State>(() => (tokens.get('guest') ? { kind: 'loading' } : { kind: 'loggedOut' }))

  const fail = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('guest')
      setState({ kind: 'loggedOut' })
    } else {
      setState((s) => (s.kind === 'ready' ? s : { kind: 'error' }))
    }
  }, [])

  const load = useCallback(async () => {
    const token = tokens.get('guest')
    if (!token) return
    try {
      setState({ kind: 'ready', market: await api<MarketData>('/api/market', { token }) })
    } catch (err) {
      fail(err)
    }
  }, [fail])

  useEffect(() => {
    // The first load and the timer both refresh the market from outside React's render
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
    const timer = setInterval(load, POLL_MS)
    const wake = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', wake)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [load])

  if (state.kind === 'loading') return <Screen><p className="text-center text-slate-500">{t('common.loading')}</p></Screen>
  if (state.kind !== 'ready') {
    return (
      <Screen>
        <Card className="text-center text-lg font-medium">
          {t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')}
        </Card>
      </Screen>
    )
  }

  const { market } = state
  // A prize waiting to be picked up comes first: the guest shows this screen at the stand
  const prizes = [...market.prizes].sort((a, b) => Number(waiting(b)) - Number(waiting(a)))
  return (
    <Screen>
      <Link to="/app" className="flex items-center gap-1 text-sm font-medium text-slate-600">
        <ChevronLeft className="size-4" aria-hidden />
        {t('feed.toFeed')}
      </Link>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t('market.title')}</h1>
        <span className="flex items-center gap-1.5 text-lg font-semibold text-amber-700">
          <Coins className="size-5" aria-hidden />
          {t('feed.coins', { count: market.coins })}
        </span>
      </div>
      {!market.open && (
        <p className="flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-3 font-medium text-slate-700">
          <Lock className="size-4 shrink-0" aria-hidden />
          {market.opens_at ? t('market.opensAt', { time: hhmm(market.opens_at) }) : t('market.opensSoon')}
        </p>
      )}
      {prizes.length === 0 && <p className="py-8 text-center text-slate-500">{t('market.empty')}</p>}
      <ul className="flex flex-col gap-3">
        {prizes.map((prize) => (
          <li key={prize.id}>
            <PrizeCard prize={prize} market={market} onChange={(m) => setState({ kind: 'ready', market: m })} onFail={fail} />
          </li>
        ))}
      </ul>
    </Screen>
  )
}

const waiting = (p: Prize) => p.code !== null && p.issued_at === null

function PrizeCard({ prize, market, onChange, onFail }:
  { prize: Prize; market: MarketData; onChange: (m: MarketData) => void; onFail: (err: unknown) => void }) {
  const { t } = useTranslation()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function buy() {
    setBusy(true)
    setError('')
    try {
      onChange(await api<MarketData>(`/api/market/${prize.id}/buy`, { token: tokens.get('guest'), method: 'POST' }))
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401 && typeof err.detail === 'string') {
        setError(t(`market.errors.${err.detail}`, { defaultValue: t('common.error') }))
        // Show the new count, coins or opening the server answered with
        api<MarketData>('/api/market', { token: tokens.get('guest') }).then(onChange).catch(onFail)
      } else if (err instanceof ApiError && err.status === 401) {
        onFail(err)
      } else {
        setError(t('common.error'))
      }
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  const short = prize.price - market.coins
  return (
    <Card className={`flex flex-col gap-3 ${waiting(prize) ? 'ring-2 ring-emerald-500' : ''}`}>
      <div className="flex flex-wrap items-center gap-2">
        <PartnerBadge name={prize.partner} />
        {!prize.code && <span className="text-sm text-slate-500">{t('market.left', { count: prize.left })}</span>}
      </div>
      <p className="text-lg font-medium">{prize.name}</p>
      <span className="flex items-center gap-1 text-sm font-medium text-amber-700">
        <Coins className="size-4" aria-hidden />
        {t('feed.coins', { count: prize.price })}
      </span>
      {prize.code && prize.issued_at && (
        <p className="flex items-center gap-1 font-medium text-emerald-700">
          <Check className="size-5" aria-hidden />
          {t('market.received')}
        </p>
      )}
      {prize.code && !prize.issued_at && (
        <div className="flex flex-col items-center gap-3 rounded-xl bg-emerald-50 p-4 text-center">
          <p className="font-medium text-emerald-900">{t('market.goToStand', { partner: prize.partner })}</p>
          <QRCodeSVG value={`${window.location.origin}/stand/${prize.code}`} size={220} marginSize={2} className="h-auto w-full max-w-[220px]" />
          <p className="font-mono text-2xl font-semibold tracking-widest">{t('market.code', { code: prize.code.toUpperCase() })}</p>
        </div>
      )}
      {!prize.code && prize.left === 0 && <Button disabled>{t('market.soldOut')}</Button>}
      {!prize.code && prize.left > 0 && !market.open && (
        <Button disabled>
          <Lock className="mr-2 size-4" aria-hidden />
          {t('market.exchange')}
        </Button>
      )}
      {!prize.code && prize.left > 0 && market.open && short > 0 && <Button disabled>{t('market.short', { count: short })}</Button>}
      {!prize.code && prize.left > 0 && market.open && short <= 0 && !confirming && (
        <Button onClick={() => setConfirming(true)}>{t('market.exchange')}</Button>
      )}
      {!prize.code && prize.left > 0 && market.open && short <= 0 && confirming && (
        <div className="flex flex-col gap-3">
          <p className="text-slate-700">
            {t('market.confirm', { price: t('feed.coins', { count: prize.price }), name: prize.name })}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" disabled={busy} onClick={() => setConfirming(false)}>{t('market.cancel')}</Button>
            <Button disabled={busy} onClick={buy}>{t('market.yes')}</Button>
          </div>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </Card>
  )
}
