type Place = { place: number; name: string; points: number; level: string }
export type Rating = {
  frozen: boolean
  top: (Place & { me: boolean })[]
  // The guest's own place; null when they aren't ranked
  me: { place: number; points: number } | null
}
export type Hall = { frozen: boolean; top: Place[] }
type HostPlace = { place: number; first_name: string; last_name: string; company: string; points: number }
export type Frozen = { frozen: boolean; top: HostPlace[] }
