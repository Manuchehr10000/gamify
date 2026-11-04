import { useEffect, useSyncExternalStore } from 'react'
import { api } from '../../api'

// The event's look: one skin per event, set by an admin in «Настройки». Each has a dark theme for guests and the hall
// and a light one for staff and admins; layout, words and behaviour are the same in all of them.
const SKINS = ['console', 'steampunk', 'space', 'ornament'] as const
export type Skin = (typeof SKINS)[number]
export type Shade = 'dark' | 'light'

export const THEMES: Record<Skin, Record<Shade, string>> = {
  console: { dark: 'console', light: 'label' },
  steampunk: { dark: 'brass', light: 'parchment' },
  space: { dark: 'orbit', light: 'station' },
  ornament: { dark: 'lapis', light: 'suzani' },
}

// Each skin's faces are their own stylesheet, fetched when a page first shows that skin
const FONTS: Record<Skin, () => Promise<unknown>> = {
  console: () => import('./fonts/console.css'),
  steampunk: () => import('./fonts/steampunk.css'),
  space: () => import('./fonts/space.css'),
  ornament: () => import('./fonts/ornament.css'),
}

const KEY = 'skin'
const isSkin = (v: unknown): v is Skin => SKINS.includes(v as Skin)

// The last skin this phone saw, so a page opens straight in it, also with no network
function stored(): Skin | null {
  try {
    const v = localStorage.getItem(KEY)
    return isSkin(v) ? v : null
  } catch {
    return null
  }
}

let remembered = stored()
let current: Skin = remembered ?? 'console'
const listeners = new Set<() => void>()

// From every /api/version answer: kept for the next page (Console too), and a new skin switches every open console
// screen at once
export function setSkin(skin: unknown) {
  if (!isSkin(skin)) return
  if (skin !== remembered) {
    try {
      localStorage.setItem(KEY, skin)
      remembered = skin
    } catch {
      // Private mode: this page still switches, the next one asks the server
    }
  }
  if (skin === current) return
  current = skin
  listeners.forEach((l) => l())
}

// The first paint waits for the skin and its faces' stylesheet, so it never flashes Console or the fallback faces
// first. A phone that has never seen a skin asks the server once; with no answer in time it opens in Console.
export async function skinReady(): Promise<void> {
  if (!stored()) {
    await api<{ skin: string }>('/api/version', { timeoutMs: 2000 }).then(({ skin }) => setSkin(skin)).catch(() => {})
  }
  await loadFonts(current).catch(() => {})
}

function subscribe(l: () => void) {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}

export function useSkin(): Skin {
  return useSyncExternalStore(subscribe, () => current)
}

const loading = new Map<Skin, Promise<unknown>>()

// Fetches a skin's faces' stylesheet once; a failed fetch is tried again next time
function loadFonts(skin: Skin): Promise<unknown> {
  let p = loading.get(skin)
  if (!p) {
    p = FONTS[skin]().catch((e) => {
      loading.delete(skin)
      throw e
    })
    loading.set(skin, p)
  }
  return p
}

// The admin's skin previews show each skin in its own faces; only /admin/settings loads them, every other page
// loads just the event's skin
export function usePreviewFonts(skin: Skin) {
  useEffect(() => {
    loadFonts(skin).catch(() => {})
  }, [skin])
}

const kept = new Set<Skin>()

// Loads the event skin's faces, then asks the offline worker to keep that stylesheet and its fonts, so the skin keeps
// its fonts with the network off even when they were fetched before the worker took over the page (keep in step with
// public/sw.js)
export function useSkinFonts(skin: Skin) {
  useEffect(() => {
    if (kept.has(skin)) return
    kept.add(skin)
    loadFonts(skin).then(() => {
      if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return
      return navigator.serviceWorker.ready.then((reg) => {
        const css = performance.getEntriesByType('resource').map((e) => new URL(e.name))
          .filter((u) => u.origin === location.origin && u.pathname.startsWith('/assets/') && u.pathname.endsWith('.css'))
        reg.active?.postMessage({ keep: css.map((u) => u.pathname) })
      })
    }).catch(() => kept.delete(skin))
  }, [skin])
}
