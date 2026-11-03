import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { InlineConfirm } from '../components/console/rewards'
import { Amount, Button, Callout, Icon, Loading, MessageCard, PageHeader, Screen } from '../components/console/ui'
import { hhmm } from '../feed'

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

  if (state.kind === 'loading') return <Screen><Loading /></Screen>
  if (state.kind !== 'ready') {
    return (
      <Screen>
        <MessageCard icon="alert" title={t(state.kind === 'loggedOut' ? 'welcome.notFound' : 'common.error')} />
      </Screen>
    )
  }

  const { market } = state
  // A prize waiting to be picked up comes first: the guest shows this screen at the stand
  const prizes = [...market.prizes].sort((a, b) => Number(waiting(b)) - Number(waiting(a)))
  return (
    <Screen>
      <PageHeader
        title={t('market.title')}
        back={{ to: '/app', label: t('feed.toFeed') }}
        aside={<span className="gc-crt gc-market-balance"><Amount kind="coins" count={market.coins} /></span>}
      />
      {!market.open && (
        <Callout tone="locked">
          {market.opens_at ? t('market.opensAt', { time: hhmm(market.opens_at) }) : t('market.opensSoon')}
        </Callout>
      )}
      {prizes.length === 0 && <MessageCard icon="bag" title={t('market.empty')} />}
      <ul className="gc-prize-list">
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
  const canBuy = !prize.code && prize.left > 0 && market.open && short <= 0
  return (
    <article className={`gc-prize-card ${waiting(prize) ? 'gc-prize-card--waiting' : ''}`}>
      <div className="gc-prize-card__meta">
        <span className="gc-prize-card__partner gc-caption">
          <Icon name="star" size={12} />
          <span className="gc-prize-card__partner-name">{prize.partner}</span>
        </span>
        {!prize.code && <span className="gc-prize-card__stock gc-body-s">{t('market.left', { count: prize.left })}</span>}
      </div>
      <p className="gc-prize-card__name gc-body-l">{prize.name}</p>
      <div className="gc-prize-card__price"><Amount kind="coins" count={prize.price} /></div>
      {prize.code && prize.issued_at && (
        <p className="gc-prize-card__received gc-body">
          <Icon name="check" size={20} />
          <span>{t('market.received')}</span>
        </p>
      )}
      {prize.code && !prize.issued_at && (
        <div className="gc-prize-card__pickup">
          <p className="gc-prize-card__pickup-text gc-body">
            <span className="gc-prize-card__pickup-icon"><Icon name="qr" size={20} /></span>
            <span>{t('market.goToStand', { partner: prize.partner })}</span>
          </p>
          <div className="gc-prize-card__qr">
            <QRCodeSVG value={`${window.location.origin}/stand/${prize.code}`} size={220} marginSize={2} />
          </div>
          <p className="gc-prize-card__code">{t('market.code', { code: prize.code.toUpperCase() })}</p>
        </div>
      )}
      {!prize.code && (
        <div className="gc-prize-card__action">
          {prize.left === 0 && <Button variant="outline" disabled>{t('market.soldOut')}</Button>}
          {prize.left > 0 && !market.open && <Button disabled icon="lock">{t('market.exchange')}</Button>}
          {prize.left > 0 && market.open && short > 0 && <Button disabled>{t('market.short', { count: short })}</Button>}
          {canBuy && !confirming && <Button onClick={() => setConfirming(true)}>{t('market.exchange')}</Button>}
          {canBuy && confirming && (
            <InlineConfirm
              question={t('market.confirm', { price: t('feed.coins', { count: prize.price }), name: prize.name })}
              busy={busy}
              onConfirm={buy}
              onCancel={() => setConfirming(false)}
            />
          )}
        </div>
      )}
      {error && (
        <p className="gc-prize-card__error gc-body-s" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </p>
      )}
    </article>
  )
}
