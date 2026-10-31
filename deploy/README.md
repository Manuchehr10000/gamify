# Deploy (Cloudflare)

One Worker per environment serves the built frontend and passes `/api/*` and `/b/*` to the FastAPI backend, which runs in a Cloudflare Container (`Dockerfile`, built from `backend/`). Postgres lives on Neon. App and API share one address.

`.github/workflows/deploy.yml` deploys `dev` after the Ship check passes on it. Never deploy by hand.

## One-time setup (owner)

1. **Cloudflare**: on the Workers Paid plan ($5/month; Containers need it). Note the account ID and the `workers.dev` subdomain (Workers & Pages → your subdomain).
2. **Cloudflare API token**: My Profile → API Tokens → Create Token → "Edit Cloudflare Workers" template, scoped to this account. If the first deploy says the token can't push the container image, add the Containers permission the error names.
3. **Neon**: create a project, then copy the connection string of its database for dev.
4. **GitHub** (repo → Settings → Environments → New environment `dev`):
   - secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DATABASE_URL` (the Neon string), `DESK_PIN` (long), `ADMIN_PASSWORD`
   - variable: `APP_URL` = `https://gamify-dev.<your-subdomain>.workers.dev`

The first deploy sets the secrets in the step after the Worker goes up: open the app only when the Deploy job is green.

## Run it locally

Needs Docker running. In `deploy/`: `npm install`, put test values in `.dev.vars` (git-ignored: `DATABASE_URL`, `DESK_PIN`, `ADMIN_PASSWORD`, `APP_URL=http://localhost:8787`), build the frontend, then `npx wrangler dev --env dev`. The container reaches a Postgres on your Mac at `host.docker.internal`.

## Watch for

The Worker retries once when the runtime drops its connection to the container before the request reaches the app (seen locally after each badge redirect). After a deploy, Workers & Pages → gamify-dev → Logs shows any `Error proxying request to container` lines; tell Claude if they appear.
