import { useTranslation } from 'react-i18next'
import { BADGE_ICONS, type Badge } from '../badges'

// Small icons beside a name in the rating and the hall
export function BadgeIcons({ badges, className = '' }: { badges: Badge[]; className?: string }) {
  const { t } = useTranslation()
  if (badges.length === 0) return null
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 ${className}`}>
      {badges.map((b) => {
        const Icon = BADGE_ICONS[b]
        return <Icon key={b} className="size-[1em]" role="img" aria-label={t(`badges.${b}.name`)} />
      })}
    </span>
  )
}
