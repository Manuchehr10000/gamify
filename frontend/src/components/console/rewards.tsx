import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { condition, type HeldBadge, type ShelfBadge } from '../../badges'
import { badgeIcon, splitNumber } from './glyphs'
import { Amount, Button, Icon } from './ui'

const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

// The quiz clock on a screen panel. In the last 10 seconds it turns red and says «Мало времени» in words too;
// screen readers hear the label, not every tick of the digits
export function CountdownTimer({ seconds }: { seconds: number }) {
  const { t } = useTranslation()
  const low = seconds <= 10
  const left = t('quiz.secondsLeft', { time: mmss(seconds) })
  // «Осталось 00:42»: the word over the panel, the time on it
  const [word, time] = splitNumber(left)
  return (
    <div className={`gc-countdown-timer ${low ? 'gc-countdown-timer--low' : ''}`} role="timer" aria-label={low ? `${t('quiz.lowTime')}. ${left}` : left}>
      <p className="gc-countdown-timer__head gc-label" aria-hidden>
        <Icon name={low ? 'alert' : 'timer'} size={16} />
        <span>{low ? t('quiz.lowTime') : word.trim()}</span>
      </p>
      <div className="gc-countdown-timer__screen gc-crt">
        <span className="gc-countdown-timer__time gc-score-xl gc-num gc-glow" aria-hidden>{time}</span>
      </div>
    </div>
  )
}

const LETTERS = ['A', 'B', 'C', 'D']

// «Вопрос 1 из N», the question and its answers as lettered switches; the one just sent stays pressed
export function QuizQuestion({ number, total, text, options, selected, disabled, onSelect }: {
  number: number
  total: number
  text: string
  options: { n: number; text: string }[]
  selected: number | null
  disabled: boolean
  onSelect: (n: number) => void
}) {
  const { t } = useTranslation()
  const id = `quiz-question-${number}`
  return (
    <section className="gc-quiz-question" aria-labelledby={id}>
      <p className="gc-quiz-question__progress gc-label">
        <Icon name="quiz" size={16} />
        <span>{t('quiz.progress', { n: number, total })}</span>
      </p>
      <p id={id} className="gc-quiz-question__text gc-body-l">{text}</p>
      <div className="gc-quiz-question__options" role="group" aria-labelledby={id}>
        {options.map((o, i) => (
          <button
            key={o.n}
            type="button"
            disabled={disabled}
            aria-pressed={selected === o.n}
            className={`gc-quiz-question__option ${selected === o.n ? 'gc-quiz-question__option--selected' : ''}`}
            onClick={() => onSelect(o.n)}
          >
            <span className="gc-quiz-question__letter gc-display-s" aria-hidden>{LETTERS[i] ?? i + 1}</span>
            <span className="gc-quiz-question__option-text gc-body">{o.text}</span>
          </button>
        ))}
      </div>
    </section>
  )
}

// An in-card question with «Отмена» and «Подтвердить» side by side, in place of a dialog
export function InlineConfirm({ question, busy, onConfirm, onCancel }:
  { question: string; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="gc-inline-confirm" role="group" aria-label={question}>
      <p className="gc-inline-confirm__question gc-label">{question}</p>
      <div className="gc-inline-confirm__actions">
        <Button variant="outline" disabled={busy} onClick={onCancel}>{t('market.cancel')}</Button>
        <Button busy={busy} onClick={onConfirm}>{t('market.yes')}</Button>
      </div>
    </div>
  )
}

export function SectionHeading({ children }: { children: ReactNode }) {
  return <h2 className="gc-section-heading gc-display-m">{children}</h2>
}

// Small pixel icons of the badges held, beside a name in the rating and the hall; each one named for screen readers
export function BadgeIcons({ badges }: { badges: HeldBadge[] }) {
  if (badges.length === 0) return null
  return (
    <span className="gc-badge-icons">
      {badges.map((b) => <Icon key={b.code} name={badgeIcon(b)} size={16} label={b.name} />)}
    </span>
  )
}

// One badge on the profile: held in colour with a check, or greyed with the lock and its condition;
// screen readers hear «получен» or «не получен», not only the colour. The condition is written from the badge's rule
export function BadgeTile({ badge }: { badge: ShelfBadge }) {
  const { t } = useTranslation()
  const held = badge.held
  return (
    <div className={`gc-badge-tile gc-badge-tile--${held ? 'held' : 'locked'}`}>
      <span className="gc-badge-tile__disc"><Icon name={badgeIcon(badge)} size={24} /></span>
      <span className="gc-badge-tile__body">
        <span className="gc-badge-tile__name gc-body">{badge.name}</span>
        {held ? (
          <span className="gc-sr">{t('badges.held')}</span>
        ) : (
          <span className="gc-badge-tile__cond gc-body-s">
            <span className="gc-badge-tile__lock"><Icon name="lock" size={16} /></span>
            <span className="gc-sr">{`${t('badges.notHeld')}: `}</span>
            <span>{condition(t, badge)}</span>
          </span>
        )}
      </span>
      {held && <span className="gc-badge-tile__mark"><Icon name="check" size={20} /></span>}
    </div>
  )
}

// One place of the top list: place, name with badges and level, points; my own row says «Вы»
export function LeaderboardRow({ place, name, level, badges, points, me }:
  { place: number; name: string; level: string; badges: HeldBadge[]; points: number; me: boolean }) {
  const { t } = useTranslation()
  return (
    <div className={`gc-leaderboard-row ${place <= 3 ? 'gc-leaderboard-row--top' : ''} ${me ? 'gc-leaderboard-row--me' : ''}`}>
      <span className="gc-leaderboard-row__place gc-score-m gc-num">{place}</span>
      <span className="gc-leaderboard-row__who">
        <span className="gc-leaderboard-row__line">
          <span className="gc-leaderboard-row__name gc-body">{name}</span>
          <BadgeIcons badges={badges} />
          {me && <span className="gc-leaderboard-row__me gc-caption">{t('rating.you')}</span>}
        </span>
        {level && <span className="gc-leaderboard-row__level gc-caption">{level}</span>}
      </span>
      <span className="gc-leaderboard-row__points"><Amount kind="points" count={points} size="s" /></span>
    </div>
  )
}
