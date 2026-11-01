import { CircleAlert, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Task } from '../feed'

// A moderator's word on what the guest sent: send again, or rejected with a warning
export function ReviewNote({ task }: { task: Task }) {
  const { t } = useTranslation()
  if (task.review === 'retake' && !task.done) {
    return (
      <p className="flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-amber-900">
        <RotateCcw className="size-5 shrink-0" aria-hidden />
        {t('review.retake')}
      </p>
    )
  }
  if (task.review === 'penalty') {
    return (
      <p className="flex items-start gap-2 rounded-xl bg-red-50 px-4 py-3 text-red-900">
        <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
        {t('review.penalty')}
      </p>
    )
  }
  return null
}
