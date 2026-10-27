import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, tokens } from '../api'
import { Button, Card, Screen } from '../components/ui'

type Me = { first_name: string; consented: boolean; arrival_points: number }
type State = { kind: 'loading' } | { kind: 'notFound' } | { kind: 'error' } | { kind: 'ready'; me: Me }

// /b/<code> lands here with the login in the fragment; keep it and clean the address bar
function firstState(): State {
  const fresh = new URLSearchParams(window.location.hash.slice(1)).get('token')
  if (fresh) {
    tokens.set('guest', fresh)
    window.history.replaceState(null, '', window.location.pathname)
  }
  const badgeError = new URLSearchParams(window.location.search).get('error') === 'badge'
  return badgeError || !tokens.get('guest') ? { kind: 'notFound' } : { kind: 'loading' }
}

export function Welcome() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [state, setState] = useState<State>(firstState)

  useEffect(() => {
    if (state.kind !== 'loading') return
    api<Me>('/api/me', { token: tokens.get('guest') })
      .then((me) => setState({ kind: 'ready', me }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          tokens.clear('guest')
          setState({ kind: 'notFound' })
        } else {
          setState({ kind: 'error' })
        }
      })
  }, [state.kind])

  async function agree() {
    try {
      const me = await api<Me>('/api/consent', { token: tokens.get('guest'), method: 'POST' })
      setState({ kind: 'ready', me })
    } catch {
      setState({ kind: 'error' })
    }
  }

  if (state.kind === 'loading') return <Screen><p className="text-center text-slate-500">{t('common.loading')}</p></Screen>
  if (state.kind === 'notFound' || state.kind === 'error') {
    return (
      <Screen>
        <Card className="text-center text-lg font-medium">
          {t(state.kind === 'notFound' ? 'welcome.notFound' : 'common.error')}
        </Card>
      </Screen>
    )
  }
  const { me } = state
  if (!me.consented) {
    return (
      <Screen>
        <Card className="flex flex-col gap-5">
          <p className="text-base leading-relaxed">{t('welcome.consent')}</p>
          <Button onClick={agree}>{t('welcome.ok')}</Button>
        </Card>
      </Screen>
    )
  }
  return (
    <Screen>
      <Card className="flex flex-col items-center gap-4 py-10 text-center">
        <h1 className="text-2xl font-semibold">{t('welcome.hello', { name: me.first_name })}</h1>
        {me.arrival_points > 0 && (
          <p className="rounded-2xl bg-emerald-50 px-4 py-2 text-lg font-medium text-emerald-700">
            {t('welcome.points', { points: me.arrival_points })}
          </p>
        )}
        <Button className="mt-4 w-full" onClick={() => navigate('/app/tasks')}>{t('welcome.toTasks')}</Button>
      </Card>
    </Screen>
  )
}
