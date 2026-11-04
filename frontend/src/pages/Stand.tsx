import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card, Icon, Loading, MessageCard, Screen } from '../components/console/ui'
import { hhmm } from '../feed'

type Handover = { prize: string; partner: string; first_name: string; issued_at: string | null }
type Issue = { result: 'issued' | 'already'; handover: Handover }

type State =
  | { kind: 'loading' }
  | { kind: 'message'; text: string }
  | { kind: 'ready'; handover: Handover; issuedNow: boolean }

// Stand staff scan the QR on a guest's /market screen with their phone camera; it opens here
export function Stand() {
  const { t } = useTranslation()
  const code = useParams().code ?? ''
  const [token, setToken] = useState(tokens.get('stand'))
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [busy, setBusy] = useState(false)

  const fail = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('stand')
      setToken(null)
    } else if (err instanceof ApiError && err.status === 404) {
      setState({ kind: 'message', text: t('stand.notFound') })
    } else {
      setState({ kind: 'message', text: t('common.error') })
    }
  }, [t])

  useEffect(() => {
    if (!token) return
    api<Handover>(`/api/stand/${encodeURIComponent(code)}`, { token })
      .then((handover) => setState({ kind: 'ready', handover, issuedNow: false }))
      .catch(fail)
  }, [code, token, fail])

  async function issue() {
    setBusy(true)
    try {
      const r = await api<Issue>(`/api/stand/${encodeURIComponent(code)}/issue`, { token, method: 'POST' })
      setState({ kind: 'ready', handover: r.handover, issuedNow: r.result === 'issued' })
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  if (!token) return <StaffLogin role="stand" onLogin={setToken} />

  if (state.kind === 'loading') return <Screen theme="light" center><Loading /></Screen>
  if (state.kind === 'message') return <Screen theme="light" center><MessageCard icon="alert" title={state.text} /></Screen>

  const { handover, issuedNow } = state
  return (
    <Screen theme="light" center>
      <Card className="gc-handover">
        <span className="gc-prize-card__partner gc-body-s">
          <Icon name="star" size={16} />
          <span className="gc-prize-card__partner-name">{handover.partner}</span>
        </span>
        <p className="gc-handover__prize gc-body-l">{handover.prize}</p>
        <p className="gc-handover__guest gc-body">{t('stand.guest', { name: handover.first_name })}</p>
        {issuedNow && (
          <p className="gc-handover__result gc-handover__result--issued gc-body-l" role="status">
            <Icon name="check" size={24} />
            {t('stand.issued')}
          </p>
        )}
        {!issuedNow && handover.issued_at && (
          <p className="gc-handover__result gc-handover__result--already gc-body-l" role="alert">
            <Icon name="alert" size={24} />
            {t('stand.already', { time: hhmm(handover.issued_at) })}
          </p>
        )}
        {!handover.issued_at && (
          <div className="gc-handover__action">
            <Button size="lg" icon="check" busy={busy} onClick={issue}>{t('stand.issue')}</Button>
          </div>
        )}
      </Card>
    </Screen>
  )
}
