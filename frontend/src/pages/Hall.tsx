import { Lock, WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { Hall as HallData } from '../rating'

const POLL_MS = 10_000

// The hall's big screen: no login, read-only. A dropped network keeps the last top 10 until it comes back
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
    <main className="flex min-h-dvh flex-col bg-slate-950 px-[4vw] py-[4vh] text-white">
      <header className="flex items-baseline justify-between gap-6">
        <h1 className="text-[clamp(2rem,5vw,5rem)] font-bold leading-tight">{t('hall.forum')}</h1>
        <p className="text-[clamp(1.25rem,3vw,3rem)] font-semibold text-emerald-400">{t('hall.title')}</p>
      </header>
      {hall?.frozen && (
        <p className="mt-[2vh] flex items-center gap-3 text-[clamp(1rem,2vw,2rem)] font-medium text-amber-300">
          <Lock className="size-[1em]" aria-hidden />
          {t('hall.frozen')}
        </p>
      )}
      {hall && hall.top.length === 0 && (
        <p className="m-auto text-[clamp(1.5rem,3vw,3rem)] text-slate-400">{t('hall.empty')}</p>
      )}
      {hall && hall.top.length > 0 && (
        <ol className="mt-[3vh] flex flex-1 flex-col justify-around">
          {hall.top.map((r) => (
            <li
              key={r.place}
              className="flex items-center gap-[2vw] border-b border-slate-800 py-[0.8vh] text-[clamp(1.25rem,3.6vw,4rem)] last:border-0"
            >
              <span className={`w-[2.5ch] text-right font-bold tabular-nums ${r.place <= 3 ? 'text-amber-300' : 'text-slate-400'}`}>
                {r.place}
              </span>
              <span className="flex-1 truncate font-semibold">{r.name}</span>
              <span className="font-bold tabular-nums text-emerald-400">{r.points}</span>
            </li>
          ))}
        </ol>
      )}
      {offline && (
        <p className="mt-[2vh] flex items-center gap-2 text-sm text-slate-500">
          <WifiOff className="size-4" aria-hidden />
          {t('hall.offline')}
        </p>
      )}
    </main>
  )
}
