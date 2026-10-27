import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from '../api'
import { StaffLogin } from '../components/StaffLogin'
import { Button, Card, Input, Screen } from '../components/ui'

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
      <Screen>
        <Card className="flex flex-col items-center gap-4 text-center">
          <h1 className="text-2xl font-semibold">{shown.first_name} {shown.last_name}</h1>
          {shown.company && <p className="text-slate-500">{shown.company}</p>}
          <QRCodeSVG value={shown.link} size={280} marginSize={2} className="h-auto w-full max-w-xs" />
          <p className="text-slate-600">{t('desk.scan')}</p>
          <Button variant="outline" className="w-full" onClick={() => setShown(null)}>{t('common.back')}</Button>
        </Card>
      </Screen>
    )
  }

  if (walkIn) {
    const field = (key: keyof typeof emptyWalkIn, required = false) => (
      <Input
        placeholder={t(`desk.${key === 'first_name' ? 'firstName' : key === 'last_name' ? 'lastName' : key}`)}
        value={walkIn[key]}
        required={required}
        inputMode={key === 'phone' ? 'tel' : undefined}
        onChange={(e) => setWalkIn({ ...walkIn, [key]: e.target.value })}
      />
    )
    return (
      <Screen>
        <Card>
          <form onSubmit={addWalkIn} className="flex flex-col gap-3">
            <h1 className="text-xl font-semibold">{t('desk.addWalkIn')}</h1>
            {field('first_name', true)}
            {field('last_name')}
            {field('phone', true)}
            {field('company')}
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button>{t('desk.create')}</Button>
            <Button type="button" variant="outline" onClick={() => setWalkIn(null)}>{t('common.back')}</Button>
          </form>
        </Card>
      </Screen>
    )
  }

  return (
    <Screen>
      <h1 className="text-xl font-semibold">{t('staff.deskTitle')}</h1>
      <Input placeholder={t('desk.search')} value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {query.trim().length >= 2 && results?.length === 0 && <p className="text-slate-500">{t('desk.nothing')}</p>}
      {query.trim().length >= 2 && results?.map((g) => (
        <button
          key={g.id}
          onClick={() => setShown(g)}
          className="rounded-xl bg-white p-4 text-left shadow-sm ring-1 ring-slate-200 hover:ring-emerald-600"
        >
          <div className="font-medium">{g.last_name} {g.first_name}</div>
          <div className="text-sm text-slate-500">{[g.company, g.phone].filter(Boolean).join(' · ')}</div>
        </button>
      ))}
      <Button variant="outline" onClick={() => { setError(''); setWalkIn(emptyWalkIn) }}>{t('desk.addWalkIn')}</Button>
    </Screen>
  )
}
