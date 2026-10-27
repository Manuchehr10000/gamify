const API_URL = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(`API ${status}`)
    this.status = status
    this.detail = detail
  }
}

type Options = { token?: string | null; method?: string; json?: unknown; form?: FormData }

async function request(path: string, { token, method, json, form }: Options = {}): Promise<Response> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (json !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(API_URL + path, {
    method: method ?? (json !== undefined || form ? 'POST' : 'GET'),
    headers,
    body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail)
  }
  return res
}

export async function api<T>(path: string, options?: Options): Promise<T> {
  return (await request(path, options)).json()
}

export async function download(path: string, token: string, filename: string): Promise<void> {
  const blob = await (await request(path, { token })).blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

// Staff and guest logins are kept per role, so the desk tablet can't turn into a guest by accident
export const tokens = {
  get: (key: 'guest' | 'desk' | 'admin') => localStorage.getItem(`${key}_token`),
  set: (key: 'guest' | 'desk' | 'admin', value: string) => localStorage.setItem(`${key}_token`, value),
  clear: (key: 'guest' | 'desk' | 'admin') => localStorage.removeItem(`${key}_token`),
}
