import type { Badge } from '../../badges'

// The design system's pixel icons. Each glyph: 12 rows x 3 hex digits, one 12-bit row of the 12x12 grid,
// most significant bit on the left
const GLYPHS = {
  award: '1f830c6064624f266630c1f819819830c204',
  camera: '0000f01f87fe4024624f24f24624027fe000',
  check: '00000000300700ec1ce387703e01c0080000',
  'chevron-left': '0000180380700e01c01c00e0070038018000',
  'chevron-right': '0001801c00e00700380380700e01c0180000',
  alert: '1f86064628618618618618018614626061f8',
  quiz: '1f86064f29998198318618618014626061f8',
  clock: '1f86064628618618798798018014026061f8',
  coin: '1f86064028f19f99999999f98f14026061f8',
  external: '03f007fcd819830860841801801801801fff',
  eye: '0000000f030c4628f18f146230c0f0000000',
  flame: '0200600700f01f23f63fe7de78e78e39c1f8',
  cap: '0000601f87fefff7fe3fd2052051fb003000',
  handshake: '000000402ef7f9fd0fcabc5743c000000000',
  lock: '0000f01981081087fe7fe79e79e7fe7fe000',
  'map-pin': '1f830c6064624f246260630c1980f0060000',
  printer: '1f8108108fff8018058019f9f0f1081f8000',
  qr: 'f4f929949f6f000b5a4d6695f56925968f5d',
  retry: '000878984a02f018018018014022041f8000',
  bag: '0000f01081087fe50a4024024024027fe000',
  sparkle: '00000408e0841c03e0ff83e01c2087082000',
  star: '0600f00f0fff7fe3fc1f81f839c30c606000',
  ticket: '000000fff841801040000841801fff000000',
  timer: '0f00001f860640a8118218018014026061f8',
  trophy: '3fcdfb9f99f95fa1f80f00600600f01f81f8',
  'user-plus': '0001c03e03e21c70027f0ff8ff8ff8000000',
  users: '00038c7de7de38c000feffeffef000000000',
  'wifi-off': '8005f86069010f034c020010068064002001',
  x: '00060670e39c1f80f00f01f839c70e606000',
  zap: '01c0380700e01fc3f80700e01c0380200000',
  upload: '0600f01f836c060060060060801801fff000',
  download: '06006006006036c1f80f0060801801fff000',
  search: '3c04208108108108104203d001800c006003',
  plus: '0000600600600607fe7fe060060060060000',
} as const

export type IconName = keyof typeof GLYPHS

// Runs of lit cells per row as [x, y, width], so each glyph is a handful of crisp rects
const rects = new Map<IconName, [number, number, number][]>()

export function glyph(name: IconName): [number, number, number][] {
  const known = rects.get(name)
  if (known) return known
  const hex = GLYPHS[name]
  const out: [number, number, number][] = []
  for (let y = 0; y < 12; y++) {
    const row = parseInt(hex.slice(y * 3, y * 3 + 3), 16)
    let x = 0
    while (x < 12) {
      if ((row >> (11 - x)) & 1) {
        const start = x
        while (x < 12 && (row >> (11 - x)) & 1) x++
        out.push([start, y, x - start])
      } else {
        x++
      }
    }
  }
  rects.set(name, out)
  return out
}

// Task types and badges in pixel icons, as the lucide ones they replace; an unknown type falls back to zap
const TYPE_ICONS: Record<string, IconName> = {
  quiz: 'quiz',
  selfie: 'camera',
  action: 'zap',
  purchase: 'bag',
  registration: 'user-plus',
  networking: 'users',
  crazy: 'sparkle',
  attention: 'eye',
  territory: 'map-pin',
  pre: 'ticket',
}
export const typeIcon = (type: string): IconName => TYPE_ICONS[type] ?? 'zap'

export const BADGE_GLYPHS: Record<Badge, IconName> = {
  photo_hunter: 'camera',
  networker: 'users',
  erudite: 'cap',
  brand_friend: 'handshake',
  forum_spirit: 'flame',
}

// The first number in a translated line («+30 баллов», «до 14:30») is set in the pixel score face, the rest in the
// reading face: the language file keeps whole phrases, so the number is found rather than passed separately
export function splitNumber(text: string): [string, string, string] {
  const m = /[+\u2212-]?\d+(?:[:.,\u00a0\u202f ]\d+)*/.exec(text)
  if (!m) return [text, '', '']
  return [text.slice(0, m.index), m[0], text.slice(m.index + m[0].length)]
}
