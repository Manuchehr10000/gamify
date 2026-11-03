import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { ResultCard } from '../components/console/game'
import { Loading, MessageCard, Screen } from '../components/console/ui'
import type { Award } from '../feed'

type State =
  | { kind: 'loading' }
  | { kind: 'message'; text: string }
  | { kind: 'notFound' }
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
          setState({ kind: 'notFound' })
        } else {
          setState({ kind: 'message', text: t('common.error') })
        }
      })
  }, [code, t])

  return (
    <Screen>
      {state.kind === 'loading' && <Loading />}
      {state.kind === 'message' && <MessageCard icon="alert" title={state.text} />}
      {state.kind === 'notFound' && <ResultCard award={null} />}
      {state.kind === 'done' && <ResultCard award={state.award} />}
    </Screen>
  )
}
