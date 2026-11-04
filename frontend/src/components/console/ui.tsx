import { useLayoutEffect, type MouseEventHandler, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useConfigVersion } from '../../version'
import { glyph, splitNumber, type IconName } from './glyphs'
import { THEMES, useSkin, useSkinFonts, type Shade } from './skin'
import './console.css'

// A pixel icon in currentColor, always beside a word; alone it needs a label
export function Icon({ name, size = 24, label }: { name: IconName; size?: number; label?: string }) {
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true, focusable: false }
  return (
    <svg className="gc-icon" width={size} height={size} viewBox="0 0 12 12" fill="currentColor" shapeRendering="crispEdges" {...a11y}>
      {glyph(name).map(([x, y, w]) => <rect key={`${x}-${y}`} x={x} y={y} width={w} height={1} />)}
    </svg>
  )
}

// Eight blocks lighting up clockwise in hard steps; with reduced motion they hold a still trail
const BLOCKS = [[0, 0], [4, 0], [8, 0], [8, 4], [8, 8], [4, 8], [0, 8], [0, 4]]

export function Spinner({ size = 20, label }: { size?: number; label?: string }) {
  const blocks = (
    <svg className="gc-spinner__blocks" width={size} height={size} viewBox="0 0 11 11" fill="currentColor" shapeRendering="crispEdges" aria-hidden focusable={false}>
      {BLOCKS.map(([x, y]) => <rect key={`${x}-${y}`} className="gc-spinner__block" x={x} y={y} width={3} height={3} />)}
    </svg>
  )
  if (!label) return <span className="gc-spinner" aria-hidden>{blocks}</span>
  return (
    <span className="gc-spinner gc-spinner--labelled" role="status">
      {blocks}
      <span className="gc-spinner__label gc-body-s">{label}</span>
    </span>
  )
}

const THEME_COLOR = 'meta[name="theme-color"]'

// Puts the page in the event skin's look while a console screen is open: the skin's dark or light theme on <html>
// (so the ground shows past the page's ends), the browser bar in the ground's colour (dark for guests and the hall,
// light for staff), the pixel tab icon and content drawn up to the notch (the screen pads itself clear of it).
// It follows the skin the version poll reports, and loads only that skin's faces. Everything goes back on leaving,
// so other screens keep their look.
function useConsoleShell(shade: Shade) {
  const skin = useSkin()
  const theme = THEMES[skin][shade]
  useConfigVersion()
  useSkinFonts(skin)
  useLayoutEffect(() => {
    const root = document.documentElement
    root.dataset.theme = theme

    let meta = document.querySelector<HTMLMetaElement>(THEME_COLOR)
    const addedMeta = !meta
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'theme-color'
      document.head.append(meta)
    }
    const oldColor = meta.content
    meta.content = getComputedStyle(root).getPropertyValue('--ground').trim()

    const icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
    const oldIcon = icon?.getAttribute('href') ?? null
    icon?.setAttribute('href', '/console-icon.svg')

    const viewport = document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
    const oldViewport = viewport?.content ?? ''
    if (viewport && !oldViewport.includes('viewport-fit')) viewport.content = `${oldViewport}, viewport-fit=cover`

    return () => {
      delete root.dataset.theme
      if (addedMeta) meta.remove()
      else meta.content = oldColor
      if (icon && oldIcon !== null) icon.setAttribute('href', oldIcon)
      if (viewport) viewport.content = oldViewport
    }
  }, [theme])
}

// The console theme for a page that draws its own frame (the admin menu sits beside its <main>, not in it)
export function ConsoleTheme({ theme }: { theme: Shade }) {
  useConsoleShell(theme)
  return null
}

// The page's one <main> in a console theme; Screen for the phone column, the hall board on its own
export function Shell({ theme, className, children }: { theme: Shade; className: string; children: ReactNode }) {
  useConsoleShell(theme)
  return <main className={`gc-root ${className}`}>{children}</main>
}

// theme: light on staff screens; wide: the moderation grid; center: one card mid-screen
export function Screen({ children, theme = 'dark', wide, center }:
  { children: ReactNode; theme?: Shade; wide?: boolean; center?: boolean }) {
  return (
    <Shell theme={theme} className={`gc-screen gc-ribs ${wide ? 'gc-screen--wide' : ''} ${center ? 'gc-screen--center' : ''}`}>
      <div className="gc-screen__col">{children}</div>
    </Shell>
  )
}

export function Stripe({ className = '' }: { className?: string }) {
  return <div className={`gc-stripe ${className}`} aria-hidden><i /><i /><i /></div>
}

// aside: a small element right of the title, such as the market's coin balance
export function PageHeader({ title, back, aside }: { title: string; back?: { to: string; label: string }; aside?: ReactNode }) {
  return (
    <header className="gc-page-header">
      {back && (
        <Link to={back.to} className="gc-page-header__back gc-label">
          <Icon name="chevron-left" size={20} />
          <span>{back.label}</span>
        </Link>
      )}
      {aside ? (
        <div className="gc-page-header__row">
          <h1 className="gc-page-header__title gc-display-l">{title}</h1>
          <div className="gc-page-header__aside">{aside}</div>
        </div>
      ) : (
        <h1 className="gc-page-header__title gc-display-l">{title}</h1>
      )}
      <Stripe className="gc-page-header__stripe" />
    </header>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`gc-card ${className}`}>{children}</div>
}

type ButtonProps = {
  children: ReactNode
  variant?: 'primary' | 'outline' | 'danger'
  size?: 'md' | 'lg'
  icon?: IconName
  busy?: boolean
  disabled?: boolean
  onClick?: MouseEventHandler
  // In the app: a router link, so what is in memory (uploads on their way) survives
  to?: string
  // Out of the app: opens in a new tab
  href?: string
  // submit: sends its form (Enter in a field does too)
  type?: 'button' | 'submit'
  // false: as wide as its words, e.g. beside an admin page's title
  block?: boolean
}

// The console switch: a button, an in-app link or an outside link that all look and press the same
export function Button({ children, variant = 'primary', size = 'md', icon, busy, disabled, onClick, to, href, type = 'button', block = true }: ButtonProps) {
  const off = disabled || busy
  const className = `gc-button ${block ? 'gc-button--block' : ''} gc-button--${variant} gc-button--${size} gc-label ${off ? 'gc-button--disabled' : ''}`
  const iconSize = size === 'lg' ? 24 : 20
  const inner = (
    <>
      {busy ? <Spinner size={iconSize} /> : icon && <Icon name={icon} size={iconSize} />}
      <span className="gc-button__text">{children}</span>
    </>
  )
  if (to) return <Link to={to} className={className} onClick={onClick}>{inner}</Link>
  if (href) {
    return <a href={href} target="_blank" rel="noopener noreferrer" className={className} onClick={onClick}>{inner}</a>
  }
  return (
    <button type={type} className={className} disabled={off} aria-busy={busy || undefined} onClick={onClick}>
      {inner}
    </button>
  )
}

export function NavRow({ to, icon, label, tone = 'default' }: { to: string; icon: IconName; label: string; tone?: 'default' | 'market' }) {
  return (
    <Link to={to} className={`gc-nav-row gc-nav-row--${tone}`}>
      <span className="gc-nav-row__tile" aria-hidden><Icon name={icon} size={24} /></span>
      <span className="gc-nav-row__label gc-label">{label}</span>
      <span className="gc-nav-row__chevron" aria-hidden><Icon name="chevron-right" size={20} /></span>
    </Link>
  )
}

type Tone = 'info' | 'success' | 'warning' | 'danger' | 'offline' | 'locked'
const TONE_ICONS: Record<Tone, IconName> = { info: 'star', success: 'check', warning: 'clock', danger: 'alert', offline: 'wifi-off', locked: 'lock' }

// An inline strip: an icon, a short message (or a short list) and at most one action
export function Callout({ tone, icon, children, action }: { tone: Tone; icon?: IconName; children: ReactNode; action?: ReactNode }) {
  return (
    <div className={`gc-callout gc-callout--${tone}`} role={tone === 'danger' ? 'alert' : undefined}>
      <span className="gc-callout__icon"><Icon name={icon ?? TONE_ICONS[tone]} size={20} /></span>
      <div className="gc-callout__text gc-body">{children}</div>
      {action && <div className="gc-callout__action">{action}</div>}
    </div>
  )
}

// The whole-screen answer: loading, empty, error or not found
export function MessageCard({ title, icon, action }: { title: string; icon?: IconName; action?: ReactNode }) {
  return (
    <div className="gc-message-card">
      {icon && <span className="gc-message-card__icon gc-crt"><Icon name={icon} size={48} /></span>}
      <p className="gc-message-card__title gc-body-l">{title}</p>
      {action && <div className="gc-message-card__action">{action}</div>}
    </div>
  )
}

export function Loading() {
  const { t } = useTranslation()
  return (
    <div className="gc-message-card gc-message-card--loading">
      <Spinner size={32} label={t('common.loading')} />
    </div>
  )
}

const NUM_CLASS = { s: 'gc-score-s', m: 'gc-score-m', l: 'gc-score-l', xl: 'gc-score-xl' }
const WORD_CLASS = { s: 'gc-body-s', m: 'gc-label', l: 'gc-body-l', xl: 'gc-body-l' }
const STAR_SIZE = { s: 16, m: 20, l: 32, xl: 48 }

// Points (star, blue) or coins (coin, gold): the number in the pixel face, the word from the language file.
// Below zero (coins spent, or a balance a rejection took under zero) it reads with one true minus: «−30 монет»;
// alarm turns a negative amount red (the profile's balance)
export function Amount({ kind, count, size = 'm', signed = false, alarm = false }: {
  kind: 'points' | 'coins'
  count: number
  size?: 's' | 'm' | 'l' | 'xl'
  signed?: boolean
  alarm?: boolean
}) {
  const { t } = useTranslation()
  const negative = count < 0
  const text = negative ? `\u2212${t(`feed.${kind}`, { count: -count })}` : t(`${signed ? 'award' : 'feed'}.${kind}`, { count })
  const [before, num, after] = splitNumber(text)
  return (
    <span className={`gc-amount gc-amount--${kind === 'coins' ? 'coin' : 'points'} gc-amount--${size} ${negative && alarm ? 'gc-amount--negative' : ''}`}>
      {kind === 'coins' ? <span className="gc-amount__coin" aria-hidden /> : <Icon name="star" size={STAR_SIZE[size]} />}
      <span className="gc-amount__text">
        {before && <span className={`gc-amount__words ${WORD_CLASS[size]}`}>{before}</span>}
        <span className={`gc-amount__num gc-num ${NUM_CLASS[size]}`}>{num}</span>
        <span className={`gc-amount__words ${WORD_CLASS[size]}`}>{after}</span>
      </span>
    </span>
  )
}

export function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (checked: boolean) => void; children: ReactNode }) {
  return (
    <label className={`gc-checkbox gc-body ${checked ? 'gc-checkbox--checked' : ''}`}>
      <input type="checkbox" className="gc-checkbox__input" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="gc-checkbox__box" aria-hidden>{checked && <Icon name="check" size={12} />}</span>
      <span>{children}</span>
    </label>
  )
}

export function StatusChip({ tone, icon, children }: { tone: 'success' | 'warning' | 'danger' | 'muted'; icon?: IconName; children: ReactNode }) {
  return (
    <span className={`gc-status-chip gc-status-chip--${tone} gc-body-s`}>
      {icon ? <Icon name={icon} size={16} /> : <Spinner size={16} />}
      <span>{children}</span>
    </span>
  )
}
