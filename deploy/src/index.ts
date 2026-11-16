import { Container, getContainer } from '@cloudflare/containers'

interface Env {
  BACKEND: DurableObjectNamespace<Backend>
  APP_URL: string
  DATABASE_URL: string
  DESK_PIN: string
  ADMIN_PASSWORD: string
  STAND_PIN: string
  MODERATORS: string
  JOBS_SECRET: string
  VAPID_PUBLIC_KEY: string
  VAPID_PRIVATE_KEY: string
  VAPID_SUBJECT: string
  NEON_RESTORE_DAYS: string
}

// Runs the FastAPI backend (deploy/Dockerfile). Static assets serve the frontend;
// only /api/* and /b/* reach this Worker (run_worker_first in wrangler.jsonc).
export class Backend extends Container<Env> {
  defaultPort = 8000
  sleepAfter = '2h'
  enableInternet = true // the database lives outside Cloudflare

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env)
    this.envVars = {
      DATABASE_URL: env.DATABASE_URL,
      DESK_PIN: env.DESK_PIN,
      ADMIN_PASSWORD: env.ADMIN_PASSWORD,
      STAND_PIN: env.STAND_PIN,
      MODERATORS: env.MODERATORS,
      JOBS_SECRET: env.JOBS_SECRET,
      // Web push; any one missing and the backend sends no pushes
      VAPID_PUBLIC_KEY: env.VAPID_PUBLIC_KEY,
      VAPID_PRIVATE_KEY: env.VAPID_PRIVATE_KEY,
      VAPID_SUBJECT: env.VAPID_SUBJECT,
      // Days Neon's restore history keeps old data (wrangler.jsonc vars): the photo deletion log's last date
      NEON_RESTORE_DAYS: env.NEON_RESTORE_DAYS,
      // App and API share one address, so badge links and CORS both point at it
      PUBLIC_BASE_URL: env.APP_URL,
      FRONTEND_URL: env.APP_URL,
    }
  }
}

// What @cloudflare/containers answers (HTTP 500) when the runtime drops its connection to the container.
// Seen on dev a few times an hour, and in wrangler dev on the request after each badge redirect.
const DROPPED = ['Container suddenly disconnected', 'Error proxying request to container']

// The sends that answer with the first result, or an "already" answer that reads as done, when repeated
// after a success. Every other send still shows the error on a drop: a repeat could do it twice.
const SAFE_SENDS = [
  /^\/api\/tasks\/[^/]+\/claim$/, // photo and text claims
  /^\/api\/claims\/[^/]+\/files$/, // and their files
  /^\/api\/quiz\/[^/]+\/(start|answer|finish)$/,
  /^\/api\/scan$/, // QR scan
  /^\/api\/tasks\/[^/]+\/complete$/, // link tasks
  /^\/api\/consent$/,
  /^\/api\/submissions\/[^/]+\/decision$/, // the moderator's decision
  /^\/api\/push\/subscribe$/,
  /^\/api\/push\/[^/]+\/received$/,
  /^\/api\/hall\/logo-shows$/,
  /^\/api\/admin\/rating\/freeze$/,
  /^\/api\/admin\/(tasks|guests)\/import\/preview$/, // the two upload previews
]

function retryable(method: string, path: string): boolean {
  if (method === 'GET' || method === 'HEAD') return true
  return method === 'POST' && SAFE_SENDS.some((pattern) => pattern.test(path))
}

export default {
  async fetch(request: Request, env: Env) {
    // The job runner is reached only by the scheduled trigger below, never from outside
    // Compared decoded, as the backend routes it: /api/%6Aobs/run is /api/jobs/run there
    let path: string
    try {
      path = decodeURIComponent(new URL(request.url).pathname)
    } catch {
      return new Response('Not Found', { status: 404 })
    }
    if (path.startsWith('/api/jobs/')) return new Response('Not Found', { status: 404 })
    // One named container for everyone: it runs migrations on start
    const container = getContainer(env.BACKEND)
    if (!retryable(request.method, path)) return container.fetch(request)
    const res = await container.fetch(request.clone())
    if (res.status !== 500) return res
    const body = await res.text()
    const dropped = DROPPED.find((error) => body.startsWith(error))
    if (!dropped) return new Response(body, res)
    // Sent once more, only for reads and the sends above
    console.log(`retry: ${request.method} ${path} after «${dropped}»`)
    return container.fetch(request)
  },

  // The cron in wrangler.jsonc, every minute: the backend runs each registered job and logs it in job_runs
  async scheduled(_controller: ScheduledController, env: Env) {
    const res = await getContainer(env.BACKEND).fetch(
      new Request(`${env.APP_URL}/api/jobs/run`, { method: 'POST', headers: { 'X-Jobs-Secret': env.JOBS_SECRET } }),
    )
    console.log(`jobs: ${res.status} ${await res.text()}`)
  },
}
