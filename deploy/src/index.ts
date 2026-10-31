import { Container, getContainer } from '@cloudflare/containers'

interface Env {
  BACKEND: DurableObjectNamespace<Backend>
  APP_URL: string
  DATABASE_URL: string
  DESK_PIN: string
  ADMIN_PASSWORD: string
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
    // One named container for everyone: it runs migrations on start
    const container = getContainer(env.BACKEND)
    const res = await container.fetch(request.clone())
    if (res.status !== 500) return res
    const body = await res.text()
    if (!body.startsWith(DROPPED)) return new Response(body, res)
    return container.fetch(request)
  },
}
