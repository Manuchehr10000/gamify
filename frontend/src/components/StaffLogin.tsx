import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { TextInput } from './console/staff'
import { Button, Card, Icon, Screen } from './console/ui'

// The one login card of every staff and admin page, in the light Label look
export function StaffLogin({ role, onLogin }: { role: 'desk' | 'admin' | 'stand' | 'moderator'; onLogin: (token: string) => void }) {
  const { t } = useTranslation()
  const [secret, setSecret] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pin = role !== 'admin'

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy || !secret) return
    setBusy(true)
    setError('')
    try {
      // Each moderator has their own PIN, which tells the server who they are
      const { token } = role === 'moderator'
        ? await api<{ token: string }>('/api/moderator/login', { json: { secret } })
        : await api<{ token: string }>('/api/staff/login', { json: { role, secret } })
      tokens.set(role, token)
      onLogin(token)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? t('staff.wrong') : t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Screen theme="label" center>
      <Card className="gc-staff-login">
        <form onSubmit={submit} className="gc-staff-login__form" noValidate aria-busy={busy || undefined}>
          <div className="gc-staff-login__head">
            <Icon name="lock" size={20} />
            <h1 className="gc-staff-login__title gc-display-m">{t(`staff.${role}Title`)}</h1>
          </div>
          <TextInput
            label={t(pin ? 'staff.pin' : 'staff.password')}
            type="password"
            inputMode={pin ? 'numeric' : undefined}
            autoComplete={pin ? 'off' : 'current-password'}
            value={secret}
            onChange={setSecret}
            error={error}
            autoFocus
          />
          <Button type="submit" busy={busy} disabled={!secret}>{t('staff.enter')}</Button>
        </form>
      </Card>
    </Screen>
  )
}
