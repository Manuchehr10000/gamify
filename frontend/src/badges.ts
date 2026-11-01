import { Camera, Flame, GraduationCap, Handshake, Users, type LucideIcon } from 'lucide-react'

// The five badges in the order guests see them; names and conditions are in the language file
export const BADGES = ['photo_hunter', 'networker', 'erudite', 'brand_friend', 'forum_spirit'] as const
export type Badge = (typeof BADGES)[number]

export const BADGE_ICONS: Record<Badge, LucideIcon> = {
  photo_hunter: Camera,
  networker: Users,
  erudite: GraduationCap,
  brand_friend: Handshake,
  forum_spirit: Flame,
}
