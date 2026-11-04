import { useEffect, useRef } from 'react'
import { api } from './api'
import { setSkin } from './components/console/skin'

// Every admin save moves the config version: a page showing what the admin sets reloads within 10 seconds. The answer
// also names the event's skin, so every console screen switches its look in the same 10 seconds.
const VERSION_POLL_MS = 10_000

type Listener = (version: number) => void
const listeners = new Set<Listener>()
let timer: ReturnType<typeof setInterval> | undefined
let asking = false

// One request for every listener on the page; offline, the page's own refresh shows the saved copy
function check() {
  if (asking) return
  asking = true
  api<{ version: number; skin: string }>('/api/version', { timeoutMs: 8000 })
    .then(({ version, skin }) => {
      setSkin(skin)
      listeners.forEach((l) => l(version))
    })
    .catch(() => {})
    .finally(() => {
      asking = false
    })
}

function listen(l: Listener) {
  listeners.add(l)
  check()
  timer ??= setInterval(check, VERSION_POLL_MS)
  return () => {
    listeners.delete(l)
    if (listeners.size === 0) {
      clearInterval(timer)
      timer = undefined
    }
  }
}

// onChange: what the page reloads when an admin saves; without it the page only follows the skin
export function useConfigVersion(onChange?: () => void) {
  const callback = useRef(onChange)
  useEffect(() => {
    callback.current = onChange
  }, [onChange])

  useEffect(() => {
    let seen: number | null = null
    return listen((version) => {
      if (seen !== null && version !== seen) callback.current?.()
      seen = version
    })
  }, [])
}
