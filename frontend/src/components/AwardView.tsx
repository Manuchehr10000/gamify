import { Check, CircleAlert, Coins } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Award } from '../feed'
import { Card } from './ui'

// What a guest sees after scanning a QR or confirming a link task
export function AwardView({ award }: { award: Award }) {
  const { t } = useTranslation()
  const { result, task } = award
  return (
    <Card className="flex flex-col items-center gap-4 py-10 text-center">
      {result === 'awarded' && (
        <>
          <p className="text-4xl font-bold text-emerald-600">{t('award.points', { count: task.points })}</p>
          <p className="flex items-center gap-2 text-2xl font-semibold text-amber-600">
            <Coins className="size-6" aria-hidden />
            {t('award.coins', { count: task.coins })}
          </p>
        </>
      )}
      {result === 'already' && (
        <p className="flex items-center gap-2 text-xl font-semibold text-emerald-700">
          <Check className="size-6" aria-hidden />
          {t('award.already')}
        </p>
      )}
      {result === 'unavailable' && (
        <p className="flex items-center gap-2 text-xl font-semibold text-slate-700">
          <CircleAlert className="size-6" aria-hidden />
          {t('award.unavailable')}
        </p>
      )}
      <p className="text-base text-slate-600">{task.text}</p>
      <Link to="/app" className="mt-2 w-full rounded-xl bg-emerald-600 py-3 font-medium text-white">{t('feed.toFeed')}</Link>
    </Card>
  )
}
