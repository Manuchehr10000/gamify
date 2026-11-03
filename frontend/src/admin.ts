import type { TFunction } from 'i18next'
import { ApiError } from './api'

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
