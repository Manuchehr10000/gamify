import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { hhmm, type Award, type Feed, type Stage, type Task } from '../../feed'
import { splitNumber, typeIcon, type IconName } from './glyphs'
import { Amount, Button, Callout, Icon, Stripe } from './ui'

// The top of the feed: the level and how far the next one is, the points and coins; it opens the profile
export function Wallet({ feed }: { feed: Feed }) {
  const { t } = useTranslation()
  return (
    <Link to="/app/profile" aria-label={t('feed.toProfile')} className="gc-wallet">
      {feed.level && (
        <span className="gc-wallet__line">
          <span className="gc-wallet__level gc-label">{feed.level}</span>
          {feed.to_next !== null && <span className="gc-wallet__hint gc-body-s">{t('feed.toNext', { count: feed.to_next })}</span>}
        </span>
      )}
      <span className="gc-wallet__totals gc-crt">
        <Amount kind="points" count={feed.points} />
        <Amount kind="coins" count={feed.coins} />
      </span>
      <span className="gc-wallet__chev" aria-hidden><Icon name="chevron-right" size={20} /></span>
    </Link>
  )
}

export function StageBar({ stage, count }: { stage: Stage; count: number }) {
  const { t } = useTranslation()
  const [before, time, after] = splitNumber(t('feed.until', { time: hhmm(stage.ends_at) }))
  return (
    <div className="gc-stage-bar">
      <div className="gc-stage-bar__track" role="img" aria-label={t('feed.stageOf', { n: stage.number, count })}>
        {Array.from({ length: count }, (_, i) => (
          <i
            key={i}
            className={`gc-stage-bar__seg gc-stage-bar__seg--${i + 1 < stage.number ? 'past' : i + 1 === stage.number ? 'current' : 'future'}`}
          />
        ))}
      </div>
      <div className="gc-stage-bar__row">
        <p className="gc-stage-bar__name gc-display-m">{stage.name}</p>
        <p className="gc-stage-bar__until gc-label">
          {before}<span className="gc-stage-bar__time gc-score-m gc-num">{time}</span>{after}
        </p>
      </div>
    </div>
  )
}

// The meta row above a task: its type, the partner and a closing time
export function TaskTypeTag({ task, deadline, showType = true }: { task: Task; deadline?: string; showType?: boolean }) {
  const { t } = useTranslation()
  if (!showType && !task.partner_name && !deadline) return null
  return (
    <div className="gc-task-type-tag">
      {showType && (
        <span className="gc-task-type-tag__type">
          <span className="gc-task-type-tag__icon"><Icon name={typeIcon(task.type)} size={16} /></span>
          <span className="gc-task-type-tag__word gc-display-s">{t(`types.${task.type}`)}</span>
        </span>
      )}
      {task.partner_name && (
        <span className="gc-task-type-tag__partner gc-caption">
          <Icon name="star" size={12} />
          <span className="gc-task-type-tag__partner-name">{task.partner_name}</span>
        </span>
      )}
      {deadline && (
        <span className="gc-task-type-tag__deadline gc-caption">
          <Icon name="clock" size={12} />
          <span>{deadline}</span>
        </span>
      )}
    </div>
  )
}

export function Reward({ task, size = 's' }: { task: Task; size?: 's' | 'm' }) {
  return (
    <span className="gc-task-card__reward">
      <Amount kind="points" count={task.points} size={size} />
      <Amount kind="coins" count={task.coins} size={size} />
    </span>
  )
}

// A moderator's word on what the guest sent: send again, or rejected with a warning
export function ReviewNote({ task }: { task: Task }) {
  const { t } = useTranslation()
  if (task.review === 'retake' && !task.done) return <Callout tone="warning" icon="retry">{t('review.retake')}</Callout>
  if (task.review === 'penalty') return <Callout tone="danger">{t('review.penalty')}</Callout>
  return null
}

export function StageBanner({ stage, onClose }: { stage: Stage; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="gc-stage-banner" role="status">
      <Stripe />
      <div className="gc-stage-banner__row">
        <span className="gc-stage-banner__num gc-crt gc-glow gc-score-m gc-num" aria-hidden>{stage.number}</span>
        <div className="gc-stage-banner__body">
          <p className="gc-stage-banner__title gc-body-l">{t('feed.newStage', { name: stage.name })}</p>
          {stage.message && <p className="gc-stage-banner__message gc-body-s">{stage.message}</p>}
        </div>
        <button type="button" onClick={onClose} aria-label={t('feed.close')} className="gc-stage-banner__close">
          <Icon name="x" size={20} />
        </button>
      </div>
    </div>
  )
}

// What a guest sees after scanning a QR, confirming a link task or sending a photo or text;
// with no award it is the QR that was not found
export function ResultCard({ award }: { award: Award | null }) {
  const { t } = useTranslation()
  const result = award?.result ?? 'notFound'
  const look: Record<typeof result, { tone: string; icon: IconName; title?: string }> = {
    awarded: { tone: 'win', icon: 'trophy' },
    already: { tone: 'done', icon: 'check', title: t('award.already') },
    unavailable: { tone: 'neutral', icon: 'alert', title: t('award.unavailable') },
    limit: { tone: 'neutral', icon: 'alert', title: t('award.limit') },
    notFound: { tone: 'neutral', icon: 'alert', title: t('award.notFound') },
  }
  const { tone, icon, title } = look[result]
  return (
    <div className={`gc-result-card gc-result-card--${tone}`} role="status">
      <span className="gc-result-card__icon gc-crt"><Icon name={icon} size={48} /></span>
      {title && <p className="gc-result-card__title gc-display-m">{title}</p>}
      {award && result === 'awarded' && (
        <div className="gc-result-card__amounts gc-crt">
          <Amount kind="points" count={award.task.points} size="xl" signed />
          <Amount kind="coins" count={award.task.coins} size="l" signed />
        </div>
      )}
      {award && <p className="gc-result-card__text gc-body">{award.task.text}</p>}
      <div className="gc-result-card__action">
        <Button to="/app">{t('feed.toFeed')}</Button>
      </div>
    </div>
  )
}

// The full-screen moment: shown once per level reached and once per badge earned; «Отлично» or Escape closes it
export function LevelUp({ title, icon, onClose }: { title: string; icon?: IconName; onClose: () => void }) {
  const { t } = useTranslation()
  useEffect(() => {
    // a held key repeats: only a fresh press closes, so queued moments are not skipped unseen
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !e.repeat && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="level-up-title"
      className={`gc-root gc-level-up gc-level-up--${icon ? 'badge' : 'level'}`}
    >
      <div className="gc-level-up__trim gc-level-up__trim--top">
        <div className="gc-level-up__wood gc-wood" />
        <Stripe />
      </div>
      <div className="gc-level-up__body">
        <div className="gc-level-up__moment">
          <span className="gc-level-up__tile"><Icon name={icon ?? 'award'} size={72} /></span>
          <h1 id="level-up-title" className="gc-level-up__title gc-display-l">{title}</h1>
        </div>
        <button type="button" onClick={onClose} autoFocus className="gc-button gc-button--primary gc-label gc-level-up__close">
          {t('level.close')}
        </button>
      </div>
      <div className="gc-level-up__trim gc-level-up__trim--bottom">
        <Stripe />
        <div className="gc-level-up__wood gc-wood" />
      </div>
    </div>
  )
}
