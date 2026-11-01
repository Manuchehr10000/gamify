import { Award } from 'lucide-react'
import { useTranslation } from 'react-i18next'

// The level-up moment: the only full-screen animation in the app, shown once per level reached
export function LevelUp({ name, onClose }: { name: string; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="level-up-title"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-emerald-700 px-6 text-center text-white"
    >
      <div className="flex animate-level-up flex-col items-center gap-6">
        <span className="flex size-28 items-center justify-center rounded-full bg-amber-300 text-emerald-900 shadow-xl">
          <Award className="size-16" aria-hidden />
        </span>
        <h1 id="level-up-title" className="text-3xl font-bold leading-tight">{t('level.new', { name })}</h1>
      </div>
      <button
        onClick={onClose}
        autoFocus
        className="h-12 w-full max-w-xs rounded-xl bg-white text-base font-medium text-emerald-800 transition hover:bg-emerald-50"
      >
        {t('level.close')}
      </button>
    </div>
  )
}
