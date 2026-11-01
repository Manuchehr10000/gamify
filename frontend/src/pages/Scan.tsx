import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { AwardView } from '../components/AwardView'
import { Card, Screen } from '../components/ui'
import type { Award } from '../feed'

type State =
  | { kind: 'loading' }
  | { kind: 'message'; text: string }
  | { kind: 'done'; award: Award }

// A task's printed QR opens <site>/q/<code> in the phone's camera app; this page claims it
export function Scan() {
  const { t } = useTranslation()
  const code = useParams().code ?? ''
  const [state, setState] = useState<State>(() =>
    tokens.get('guest') ? { kind: 'loading' } : { kind: 'message', text: t('welcome.notFound') })

  useEffect(() => {
    const token = tokens.get('guest')
    if (!token) return
    api<Award>('/api/scan', { token, json: { code } })
      .then((award) => setState({ kind: 'done', award }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          tokens.clear('guest')
          setState({ kind: 'message', text: t('welcome.notFound') })
        } else if (err instanceof ApiError && err.status === 404) {
          setState({ kind: 'message', text: t('award.notFound') })
        } else {
          setState({ kind: 'message', text: t('common.error') })
        }
      })
  }, [code, t])

  return (
    <Screen>
      {state.kind === 'loading' && <p className="text-center text-slate-500">{t('common.loading')}</p>}
      {state.kind === 'message' && <Card className="text-center text-lg font-medium">{state.text}</Card>}
      {state.kind === 'done' && <AwardView award={state.award} />}
    </Screen>
  )
}
