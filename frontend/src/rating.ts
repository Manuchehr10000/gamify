import type { HeldBadge } from './badges'

// badges: the ones held now, as small icons beside the name
type Place = { place: number; name: string; points: number; level: string; badges: HeldBadge[] }
export type Rating = {
  frozen: boolean
  top: (Place & { me: boolean })[]
  // The guest's own place; null when they aren't ranked
  me: { place: number; points: number } | null
}
// auto · live («Эфир сейчас») · logos («Только логотипы») · pause, as a moderator or admin last switched it
export type HallMode = 'auto' | 'live' | 'logos' | 'pause'
// size: 1 small · 2 medium · 3 large; every: shown on every Nth logo slide
export type HallLogo = { id: number; name: string; size: number; every: number; url: string }
export type Hall = {
  frozen: boolean
  top: Place[]
  mode: HallMode
  // «Авто» shows «Эфир» from this time on; null without a schedule
  live_from: string | null
  // The server's clock when it answered
  now: string
  slide_seconds: number
  min_font_px: number
  logos: HallLogo[]
  // The countdown slide's target; null skips it
  next: { kind: 'quiz' | 'market' | 'stage'; name: string; at: string } | null
  // The latest push sent in the last 15 seconds, shown once per id
  push: { id: number; text: string } | null
  // A guest's badge marked «на экран», shown full screen like a push, once per id; null while a push shows, in «Эфир»
  // or «Пауза»
  badge: { id: number; name: string; badge: string } | null
}
type HostPlace = { place: number; first_name: string; last_name: string; company: string; points: number }
export type Frozen = { frozen: boolean; top: HostPlace[] }
