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

// What @cloudflare/containers answers when the runtime drops its connection to the container
// before the request reaches the app (the runtime marks this retryable). Seen in wrangler dev
// on the request after each badge redirect.
const DROPPED = 'Error proxying request to container'

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
    const res = await container.fetch(request.clone())
    if (res.status !== 500) return res
    const body = await res.text()
    if (!body.startsWith(DROPPED)) return new Response(body, res)
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
