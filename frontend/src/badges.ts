// The five badges in the order guests see them; names and conditions are in the language file
export const BADGES = ['photo_hunter', 'networker', 'erudite', 'brand_friend', 'forum_spirit'] as const
export type Badge = (typeof BADGES)[number]
