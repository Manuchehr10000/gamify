import { Check, CircleAlert } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { PartnerBadge } from '../components/PartnerBadge'
import { Button, Card, Screen } from '../components/ui'
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

  return (
    <Screen>
      {state.kind === 'loading' && <p className="text-center text-slate-500">{t('common.loading')}</p>}
      {state.kind === 'message' && <Card className="text-center text-lg font-medium">{state.text}</Card>}
      {state.kind === 'ready' && (
        <Card className="flex flex-col items-center gap-4 py-8 text-center">
          <PartnerBadge name={state.handover.partner} />
          <p className="text-2xl font-semibold">{state.handover.prize}</p>
          <p className="text-lg text-slate-600">{t('stand.guest', { name: state.handover.first_name })}</p>
          {state.issuedNow && (
            <p className="flex items-center gap-2 text-xl font-semibold text-emerald-700">
              <Check className="size-6" aria-hidden />
              {t('stand.issued')}
            </p>
          )}
          {!state.issuedNow && state.handover.issued_at && (
            <p className="flex items-center gap-2 text-xl font-semibold text-red-700">
              <CircleAlert className="size-6" aria-hidden />
              {t('stand.already', { time: hhmm(state.handover.issued_at) })}
            </p>
          )}
          {!state.handover.issued_at && (
            <Button className="w-full" disabled={busy} onClick={issue}>{t('stand.issue')}</Button>
          )}
        </Card>
      )}
    </Screen>
  )
}
