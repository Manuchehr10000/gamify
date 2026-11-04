import { useId, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'
import { usePhotoDeletion } from '../../admin'
import { hhmm, type Stage } from '../../feed'
import type { IconName } from './glyphs'
import { InlineConfirm } from './rewards'
import { Button, Callout, ConsoleTheme, Icon, Spinner } from './ui'

// Every admin page, in the menu's order
const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/admin/live', label: 'live.title', icon: 'zap' },
  { to: '/admin/tasks', label: 'tasksAdmin.title', icon: 'upload' },
  { to: '/admin/guests', label: 'staff.adminTitle', icon: 'users' },
  { to: '/admin/tasks/qr', label: 'qrSheet.title', icon: 'qr' },
]

// The admin page frame in the light Label look: the menu (a side menu with woodgrain trim from 768px, a top bar that
// scrolls sideways below it), one title with its actions, then the page. Printing leaves only the page content.
export function AdminShell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  const { t } = useTranslation()
  const deletion = usePhotoDeletion().notice
  return (
    <div className="gc-root gc-admin-shell gc-ribs">
      <ConsoleTheme theme="label" />
      <header className="gc-admin-shell__bar">
        <div className="gc-admin-shell__trim gc-wood" aria-hidden />
        <nav className="gc-admin-shell__nav" aria-label={t('admin.nav')}>
          <ul className="gc-admin-shell__nav-list">
            {NAV.map((item) => (
              <li key={item.to} className="gc-admin-shell__nav-li">
                {/* end: the QR sheet is not also «Задания и этапы» */}
                <NavLink
                  to={item.to}
                  end
                  className={({ isActive }) => `gc-admin-shell__nav-link gc-label ${isActive ? 'gc-admin-shell__nav-link--active' : ''}`}
                >
                  <span className="gc-admin-shell__nav-icon"><Icon name={item.icon} size={20} /></span>
                  <span>{t(item.label)}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="gc-admin-shell__main">
        <div className="gc-admin-shell__col">
          <div className="gc-admin-shell__head">
            <h1 className="gc-admin-shell__title gc-display-l">{title}</h1>
            {actions && <div className="gc-admin-shell__actions">{actions}</div>}
          </div>
          {deletion && <Callout tone="warning" icon="alert">{deletion}</Callout>}
          <div className="gc-admin-shell__body">{children}</div>
        </div>
      </main>
    </div>
  )
}

type Column = { key: string; label: string; align?: 'right' }
type Cell = string | number | null | undefined

// A real table on a desktop; below 768px each row is a card of «label: value» lines, the first column its title
export function DataTable({ columns, rows, empty, caption }:
  { columns: Column[]; rows: ({ id: string | number } & Record<string, Cell>)[]; empty?: string; caption?: string }) {
  if (rows.length === 0) {
    return (
      <div className="gc-data-table">
        {caption && <p className="gc-data-table__caption gc-label">{caption}</p>}
        {empty && <p className="gc-data-table__empty gc-body-s">{empty}</p>}
      </div>
    )
  }
  const cls = (col: Column, i: number) =>
    `${i === 0 ? 'gc-data-table__first' : ''} ${col.align === 'right' ? 'gc-data-table__right gc-num' : ''}`
  return (
    <div className="gc-data-table">
      {/* The roles keep the table read as a table when its cells become blocks on a phone */}
      <table className="gc-data-table__table" role="table">
        {caption && <caption className="gc-data-table__caption gc-label">{caption}</caption>}
        <thead className="gc-data-table__head" role="rowgroup">
          <tr role="row">
            {columns.map((col, i) => (
              <th key={col.key} scope="col" role="columnheader" className={`gc-data-table__th gc-caption ${cls(col, i)}`}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="gc-data-table__body" role="rowgroup">
          {rows.map((row) => (
            <tr key={row.id} className="gc-data-table__tr" role="row">
              {columns.map((col, i) => (
                <td key={col.key} role="cell" data-label={col.label} className={`gc-data-table__td gc-body-s ${cls(col, i)}`}>
                  <span className="gc-data-table__value">{row[col.key] ?? '—'}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// The file picker: a «Выбрать файл» key with the chosen name beside it, over the native input (Tab reaches it)
export function FileUpload({ accept, fileName, busy, onChange }:
  { accept: string; fileName?: string; busy?: boolean; onChange: (file: File | null) => void }) {
  const { t } = useTranslation()
  const id = useId()
  return (
    <div className={`gc-file-upload ${busy ? 'gc-file-upload--busy' : ''}`}>
      <label htmlFor={id} className="gc-file-upload__pick">
        <input
          id={id}
          type="file"
          className="gc-file-upload__input gc-sr"
          accept={accept}
          disabled={busy}
          aria-describedby={`${id}-name`}
          onChange={(e) => {
            onChange(e.target.files?.[0] ?? null)
            // The same file picked again (after fixing it) still counts as a pick
            e.target.value = ''
          }}
        />
        <span className="gc-file-upload__btn" aria-hidden>
          {busy ? <Spinner size={16} /> : <Icon name="upload" size={16} />}
          <span>{t('admin.chooseFile')}</span>
        </span>
        <span id={`${id}-name`} className={`gc-file-upload__name gc-body-s ${fileName ? '' : 'gc-file-upload__name--empty'}`}>
          {fileName ?? t('admin.noFile')}
        </span>
      </label>
    </div>
  )
}

type Schedule = { state: 'none' | 'before' | 'running' | 'over'; current: number | null; stages: Stage[] }

// Which stage runs now, the whole day's plan, and starting the next stage early after a yes asked in the card.
// asking: the question naming which stage ends and which starts, as the server said; null while nothing is asked
export function StageSchedule({ schedule, busy, asking, onAsk, onCancel, onAdvance }: {
  schedule: Schedule | null; busy: boolean; asking: string | null
  onAsk: () => void; onCancel: () => void; onAdvance: () => void
}) {
  const { t } = useTranslation()
  const state = schedule?.state ?? 'none'
  const stages = schedule?.stages ?? []
  const current = stages.find((s) => s.number === schedule?.current)
  const canAdvance = state === 'before' || (state === 'running' && schedule?.current !== stages.length)
  const row = (s: Stage) => {
    if (state === 'before' || (state === 'running' && s.number > (schedule?.current ?? 0))) return 'next'
    return s.number === schedule?.current ? 'current' : 'past'
  }
  const icon = { past: 'check', current: 'chevron-right', next: 'clock' } as const
  return (
    <section className={`gc-stage-schedule gc-stage-schedule--${state}`}>
      <div className="gc-stage-schedule__now">
        <p className="gc-stage-schedule__kicker gc-body-s">{t('tasksAdmin.currentStage')}</p>
        <p className="gc-stage-schedule__current gc-label">
          {current
            ? <span className="gc-num">{`${current.number}. ${current.name} · ${hhmm(current.starts_at)}–${hhmm(current.ends_at)}`}</span>
            : t(`tasksAdmin.state.${state}`)}
        </p>
      </div>
      {stages.length > 0 && (
        <ol className="gc-stage-schedule__list">
          {stages.map((s) => (
            <li key={s.number} className={`gc-stage-schedule__row gc-stage-schedule__row--${row(s)}`} aria-current={row(s) === 'current' ? 'step' : undefined}>
              <span className="gc-stage-schedule__icon"><Icon name={icon[row(s)]} size={16} /></span>
              <span className="gc-stage-schedule__num gc-score-m gc-num">{s.number}</span>
              <span className="gc-stage-schedule__name">{s.name}</span>
              <span className="gc-stage-schedule__time gc-body-s gc-num">{`${hhmm(s.starts_at)}–${hhmm(s.ends_at)}`}</span>
              {row(s) === 'current' && <span className="gc-sr">{` ${t('tasksAdmin.now')}`}</span>}
            </li>
          ))}
        </ol>
      )}
      {asking !== null
        ? <InlineConfirm question={asking} busy={busy} onCancel={onCancel} onConfirm={onAdvance} />
        : <Button variant="outline" busy={busy} disabled={!canAdvance} onClick={onAsk}>{t('tasksAdmin.next')}</Button>}
    </section>
  )
}
