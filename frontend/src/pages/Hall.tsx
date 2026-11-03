import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { BadgeIcons } from '../components/console/rewards'
import { Icon, Shell, Stripe } from '../components/console/ui'
import type { Hall as HallData } from '../rating'

const POLL_MS = 10_000

// The hall's big screen: no login, read-only, the dark board in a woodgrain frame. A dropped network keeps the last
// top 10 under «Нет связи» until it comes back
export function Hall() {
  const { t } = useTranslation()
  const [hall, setHall] = useState<HallData | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () =>
      api<HallData>('/api/hall', { timeoutMs: 8000 })
        .then((data) => {
          if (!alive) return
          setHall(data)
          setOffline(false)
        })
        .catch(() => alive && setOffline(true))
    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  return (
    <Shell theme="console" className="gc-hall-board gc-wood">
      <div className="gc-hall-board__screen">
        <header className="gc-hall-board__titles">
          <p className="gc-hall-board__event">{t('hall.forum')}</p>
          <h1 className="gc-hall-board__title gc-display-xl">{t('hall.title')}</h1>
        </header>
        <Stripe className="gc-hall-board__stripe" />
        {hall?.frozen && (
          <p className="gc-hall-board__notice gc-hall-board__notice--frozen" role="status">
            <Icon name="lock" size={32} />
            <span>{t('hall.frozen')}</span>
          </p>
        )}
        {offline && (
          <p className="gc-hall-board__notice gc-hall-board__notice--offline" role="status">
            <Icon name="wifi-off" size={24} />
            <span>{t('hall.offline')}</span>
          </p>
        )}
        {hall && hall.top.length === 0 && <p className="gc-hall-board__empty">{t('hall.empty')}</p>}
        {hall && hall.top.length > 0 && (
          <ol className="gc-hall-board__list">
            {hall.top.map((r) => (
              <li key={r.place} className={`gc-hall-board__row ${r.place <= 3 ? 'gc-hall-board__row--top' : ''}`}>
                <span className="gc-hall-board__place gc-score-l gc-num">{r.place}</span>
                <span className="gc-hall-board__who">
                  <span className="gc-hall-board__name">{r.name}</span>
                  {r.badges.length > 0 && <span className="gc-hall-board__badges"><BadgeIcons badges={r.badges} /></span>}
                  {r.level && <span className="gc-hall-board__level">{r.level}</span>}
                </span>
                <span className={`gc-hall-board__points ${r.place <= 3 ? 'gc-score-xl' : 'gc-score-l'} gc-num`}>{r.points}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Shell>
  )
}
