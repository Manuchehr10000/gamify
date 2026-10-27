import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { Button, Card, Input, Screen } from './ui'

export function StaffLogin({ role, onLogin }: { role: 'desk' | 'admin'; onLogin: (token: string) => void }) {
  const { t } = useTranslation()
  const [secret, setSecret] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { token } = await api<{ token: string }>('/api/staff/login', { json: { role, secret } })
      tokens.set(role, token)
      onLogin(token)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? t('staff.wrong') : t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Screen>
      <Card>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <h1 className="text-xl font-semibold">{t(role === 'desk' ? 'staff.deskTitle' : 'staff.adminTitle')}</h1>
          <Input
            type="password"
            inputMode={role === 'desk' ? 'numeric' : undefined}
            placeholder={t(role === 'desk' ? 'staff.pin' : 'staff.password')}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            autoFocus
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button disabled={busy || !secret}>{t('staff.enter')}</Button>
        </form>
      </Card>
    </Screen>
  )
}
