import type { TFunction } from 'i18next'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tokens } from './api'

// What a save would change in the live game; the server sends it until the save is resent with confirm
type Impact = { code: string } & Record<string, string | number | null>

function impactText(t: TFunction, impact: Impact[]): string {
  const lines = impact.map((i) => `• ${t(`settingsAdmin.impact.${i.code}`, {
    ...i, from: i.from ?? t('settingsAdmin.stageNone'), to: i.to ?? t('settingsAdmin.stageNone'),
  })}`)
  return [t('settingsAdmin.confirmTitle'), ...lines, t('settingsAdmin.confirmAsk')].join('\n')
}

// Runs a save; when it hits the live game, says what will change and resends it only if the admin agrees.
// null: the admin cancelled and nothing was saved
export async function confirmed<T>(t: TFunction, call: (confirm: boolean) => Promise<T>): Promise<T | null> {
  try {
    return await call(false)
  } catch (err) {
    const detail = err instanceof ApiError ? err.detail as { code?: string; impact?: Impact[] } : null
    if (!(err instanceof ApiError && err.status === 409 && detail?.code === 'confirm')) throw err
    if (!window.confirm(impactText(t, detail.impact ?? []))) return null
    return call(true)
  }
}

type PhotoDeletion = { date: string | null; count: number; locked: boolean }

const deletionDay = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' })

// From 7 days before the photo deletion date: the notice «1 240 фото будут удалены 15 января», with the live count
// (null before then, once nothing is left, or without an admin login), and whether the date is locked
export function usePhotoDeletion(): { notice: string | null; locked: boolean } {
  const { t } = useTranslation()
  const [state, setState] = useState<PhotoDeletion | null>(null)
  useEffect(() => {
    const token = tokens.get('admin')
    if (token) api<PhotoDeletion>('/api/admin/photo-deletion', { token }).then(setState).catch(() => setState(null))
  }, [])
  const locked = !!state?.locked
  if (!locked || !state?.date || state.count === 0) return { notice: null, locked }
  return {
    notice: t('admin.photoDeletion', {
      count: state.count, n: state.count.toLocaleString('ru-RU'), date: deletionDay.format(new Date(state.date)),
    }),
    locked,
  }
}
