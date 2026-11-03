import type { TFunction } from 'i18next'

// The badges the admin sets: the name is theirs, the rule type picks the icon and the condition's words
type BadgeRule = 'tasks' | 'all_of_type' | 'quiz_streak' | 'bonuses' | 'first_n' | 'place'
export type HeldBadge = { code: string; name: string; rule: BadgeRule }
// On the profile: every badge switched on, with its rule's numbers and filters for the greyed condition
export type ShelfBadge = HeldBadge & {
  count: number | null
  // «Тип задания» as the file writes it, e.g. «Фото, Фото+текст»; empty = any task
  kinds: string
  partner: string
  any_partner: boolean
  // «Первые N»: the task's text
  task: string
  held: boolean
}

// «5 заданий: Фото, Фото+текст», «3 задания одного партнёра», «Среди первых 3 гостей: «Селфи у стенда»»
export function condition(t: TFunction, b: ShelfBadge): string {
  const rule = b.count === null ? t(`badges.rules.${b.rule}`) : t(`badges.rules.${b.rule}`, { count: b.count })
  if (b.rule === 'first_n' && b.task) return t('badges.task', { rule, task: b.task })
  if (b.rule === 'quiz_streak' || b.rule === 'place') return rule
  const scoped = b.any_partner ? t('badges.anyPartner', { rule })
    : b.partner ? t('badges.partner', { rule, partner: b.partner }) : rule
  return b.kinds ? t('badges.kinds', { rule: scoped, kinds: b.kinds }) : scoped
}
