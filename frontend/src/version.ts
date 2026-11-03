import { useEffect, useRef } from 'react'
import { api } from './api'

// Every admin save moves the config version: a page showing what the admin sets reloads within 10 seconds
const VERSION_POLL_MS = 10_000

export function useConfigVersion(onChange: () => void) {
  const callback = useRef(onChange)
  useEffect(() => {
    callback.current = onChange
  }, [onChange])

  useEffect(() => {
    let seen: number | null = null
    let alive = true
    const check = () =>
      api<{ version: number }>('/api/version', { timeoutMs: 8000 })
        .then(({ version }) => {
          if (!alive) return
          if (seen !== null && version !== seen) callback.current()
          seen = version
        })
        // Offline: the page's own refresh shows the saved copy
        .catch(() => {})
    check()
    const timer = setInterval(check, VERSION_POLL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])
}
