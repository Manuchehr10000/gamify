import { useId, type ReactNode } from 'react'
import { Icon } from './ui'

type TextInputProps = {
  label: string
  value: string
  onChange: (value: string) => void
  type?: 'text' | 'tel' | 'password'
  inputMode?: 'numeric' | 'tel'
  autoComplete?: string
  autoFocus?: boolean
  required?: boolean
  error?: string
}

// The console's one-line field: the label always above it, the error line with an icon under it
export function TextInput({ label, value, onChange, type = 'text', inputMode, autoComplete, autoFocus, required, error }: TextInputProps) {
  const id = useId()
  return (
    <div className={`gc-text-input ${error ? 'gc-text-input--error' : ''}`}>
      <label htmlFor={id} className="gc-text-input__label gc-label">{label}</label>
      <input
        id={id}
        className="gc-text-input__field gc-body"
        type={type}
        inputMode={inputMode}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        required={required}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {error && (
        <p id={`${id}-error`} className="gc-text-input__error gc-body-s" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

// One live number on a screen panel; the label comes first for screen readers, the number shows on top
export function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="gc-stat-tile">
      <span className="gc-stat-tile__label gc-body-s">{label}</span>
      <span className="gc-stat-tile__num gc-score-l gc-num">{value}</span>
    </div>
  )
}

// A desk search result: the whole row is the switch
export function GuestRow({ name, meta, onClick }: { name: string; meta: string; onClick: () => void }) {
  return (
    <button type="button" className="gc-guest-row" onClick={onClick}>
      <span className="gc-guest-row__body">
        <span className="gc-guest-row__name gc-label">{name}</span>
        {meta && <span className="gc-guest-row__meta gc-body-s">{meta}</span>}
      </span>
      <span className="gc-guest-row__chevron" aria-hidden><Icon name="chevron-right" size={20} /></span>
    </button>
  )
}

// One QR on a light quiet zone with its title and caption
export function QrCard({ title, subtitle, caption, children }: { title: string; subtitle?: string; caption?: string; children: ReactNode }) {
  return (
    <figure className="gc-qr-card">
      <div className="gc-qr-card__quiet">{children}</div>
      <figcaption className="gc-qr-card__text">
        <p className="gc-qr-card__title gc-body-l">{title}</p>
        {subtitle && <p className="gc-qr-card__subtitle gc-body">{subtitle}</p>}
        {caption && <p className="gc-qr-card__caption gc-body-s">{caption}</p>}
      </figcaption>
    </figure>
  )
}
