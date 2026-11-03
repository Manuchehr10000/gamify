import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { GuestRow, QrCard, TextInput } from '../components/console/staff'
import { Button, Callout, Card, PageHeader, Screen } from '../components/console/ui'

type Guest = { id: number; first_name: string; last_name: string; phone: string; company: string; link: string }

const emptyWalkIn = { first_name: '', last_name: '', phone: '', company: '' }

export function Desk() {
  const { t } = useTranslation()
  const [token, setToken] = useState(tokens.get('desk'))
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Guest[] | null>(null)
  const [shown, setShown] = useState<Guest | null>(null)
  const [walkIn, setWalkIn] = useState<typeof emptyWalkIn | null>(null)
  const [error, setError] = useState('')

  function fail(err: unknown) {
    if (err instanceof ApiError && err.status === 401) {
      tokens.clear('desk')
      setToken(null)
    } else {
      setError(t('common.error'))
    }
  }

  useEffect(() => {
    if (!token || query.trim().length < 2) return
    const timer = setTimeout(() => {
      api<Guest[]>(`/api/desk/guests?q=${encodeURIComponent(query)}`, { token })
        .then((found) => { setResults(found); setError('') })
        .catch(fail)
    }, 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, token])

  async function addWalkIn(e: FormEvent) {
    e.preventDefault()
    try {
      const guest = await api<Guest>('/api/desk/guests', { token, json: walkIn })
      setWalkIn(null)
      setShown(guest)
    } catch (err) {
      fail(err)
    }
  }

  if (!token) return <StaffLogin role="desk" onLogin={setToken} />

  if (shown) {
    return (
      <Screen theme="label">
        <QrCard title={`${shown.first_name} ${shown.last_name}`} subtitle={shown.company} caption={t('desk.scan')}>
          <QRCodeSVG value={shown.link} size={280} marginSize={2} />
        </QrCard>
        <Button variant="outline" icon="chevron-left" onClick={() => setShown(null)}>{t('common.back')}</Button>
      </Screen>
    )
  }

  if (walkIn) {
    const field = (key: keyof typeof emptyWalkIn, required = false) => (
      <TextInput
        label={t(`desk.${key === 'first_name' ? 'firstName' : key === 'last_name' ? 'lastName' : key}`)}
        value={walkIn[key]}
        required={required}
        type={key === 'phone' ? 'tel' : 'text'}
        inputMode={key === 'phone' ? 'tel' : undefined}
        onChange={(value) => setWalkIn({ ...walkIn, [key]: value })}
      />
    )
    return (
      <Screen theme="label">
        <PageHeader title={t('desk.addWalkIn')} />
        <Card>
          <form onSubmit={addWalkIn} className="gc-staff-login__form">
            {field('first_name', true)}
            {field('last_name')}
            {field('phone', true)}
            {field('company')}
            {error && <Callout tone="danger">{error}</Callout>}
            <Button type="submit" icon="qr">{t('desk.create')}</Button>
            <Button variant="outline" icon="chevron-left" onClick={() => setWalkIn(null)}>{t('common.back')}</Button>
          </form>
        </Card>
      </Screen>
    )
  }

  const searching = query.trim().length >= 2
  return (
    <Screen theme="label">
      <PageHeader title={t('staff.deskTitle')} />
      <TextInput label={t('desk.search')} value={query} onChange={setQuery} autoFocus />
      {error && <Callout tone="danger">{error}</Callout>}
      {searching && results?.length === 0 && <p className="gc-empty gc-body">{t('desk.nothing')}</p>}
      {searching && results && results.length > 0 && (
        <ul className="gc-guest-list">
          {results.map((g) => (
            <li key={g.id}>
              <GuestRow
                name={`${g.last_name} ${g.first_name}`}
                meta={[g.company, g.phone].filter(Boolean).join(' · ')}
                onClick={() => setShown(g)}
              />
            </li>
          ))}
        </ul>
      )}
      <Button variant="outline" icon="user-plus" onClick={() => { setError(''); setWalkIn(emptyWalkIn) }}>{t('desk.addWalkIn')}</Button>
    </Screen>
  )
}
