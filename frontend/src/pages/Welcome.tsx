import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { splitNumber } from '../components/console/glyphs'
import { Button, Icon, Loading, MessageCard, Screen, Stripe } from '../components/console/ui'

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

  if (state.kind === 'loading') return <Screen><Loading /></Screen>
  if (state.kind === 'notFound' || state.kind === 'error') {
    return (
      <Screen>
        <MessageCard icon="alert" title={t(state.kind === 'notFound' ? 'welcome.notFound' : 'common.error')} />
      </Screen>
    )
  }
  const { me } = state
  if (!me.consented) {
    return (
      <Screen>
        <section className="gc-welcome-hero gc-welcome-hero--consent">
          <p className="gc-welcome-hero__consent gc-body">{t('welcome.consent')}</p>
          <Button onClick={agree}>{t('welcome.ok')}</Button>
        </section>
      </Screen>
    )
  }
  const [before, points, after] = splitNumber(t('welcome.points', { points: me.arrival_points }))
  return (
    <Screen>
      <section className="gc-welcome-hero">
        <Stripe />
        <div className="gc-welcome-hero__body">
          <h1 className="gc-welcome-hero__hello gc-display-l">{t('welcome.hello', { name: me.first_name })}</h1>
          {me.arrival_points > 0 && (
            <p className="gc-welcome-hero__points gc-crt gc-body-l">
              <Icon name="star" size={32} />
              <span>
                {before}<span className="gc-glow gc-score-l gc-num">{points}</span>{after}
              </span>
            </p>
          )}
          <div className="gc-welcome-hero__action">
            <Button to="/app" size="lg">{t('welcome.toTasks')}</Button>
          </div>
        </div>
      </section>
    </Screen>
  )
}
