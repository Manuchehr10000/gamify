import { useTranslation } from 'react-i18next'
import { hhmm, type Stage } from '../feed'

export function DayBar({ stage, count }: { stage: Stage; count: number }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-1.5" role="img" aria-label={t('feed.stageOf', { n: stage.number, count })}>
        {Array.from({ length: count }, (_, i) => (
          <div
            key={i}
            className={`h-2 flex-1 rounded-full ${i + 1 < stage.number ? 'bg-emerald-300' : i + 1 === stage.number ? 'bg-emerald-600' : 'bg-slate-200'}`}
          />
        ))}
      </div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-semibold">{stage.name}</p>
        <p className="shrink-0 text-sm text-slate-500">{t('feed.until', { time: hhmm(stage.ends_at) })}</p>
      </div>
    </div>
  )
}
