# Ship: how this project deploys

Written by `/mg-ship-kit:setup` from the Ship kit. Don't edit the files in this folder, `.github/workflows/ship-check.yml` or `.github/workflows/ship-secrets.yml`: rerun `/mg-ship-kit:setup` to update them.

## What runs on every push

GitHub runs the **Ship check** (`.github/workflows/ship-check.yml`, using the copy of the kit's script in this folder) on every push to `dev`, `main` and `master`. Nothing may deploy unless it passes.

- **Push to `dev`:** a push that changes only bookkeeping (contracts, `ship.json`, `CLAUDE.md`, `.gitignore`, `.gitleaksignore`, `.claude/settings.json`, the kit's files in `.github/` and its templates, the readme) passes. The project's own workflows and actions (`.github/workflows/`, `.github/actions/`) are product code, unless `ship.json` lists them under `bookkeeping` (the cloudflare track's `deploy.yml`). Any product code needs the piece that is building to pass the CTO check (size, stack, leftovers), and it must come after that piece was picked up. The check starts from the newest commit it passed on, so a failed push can't hide under a later one.
- **Secrets (every branch):** gitleaks scans each commit the push brought, not only the final files, so a key added and later deleted is still found. On `dev`, `main` and `master` the Ship check does it; on every other branch the small **Ship secret scan** (`.github/workflows/ship-secrets.yml`) does. A finding fails the run. A key that reached GitHub is exposed even on a branch nobody merges: replace it at its source. A false alarm is cleared only by the owner's one-line yes, written to `.gitleaksignore` by `ship_check.py secret-allow`; a `gitleaks:allow` comment in the code clears nothing, and a `.gitleaks.toml` in the repo is never read. History from before setup was scanned once at setup and is never blocked.
- **Env files:** a push to `dev` or `main` fails while the commit carries an env file (`.env`, `.env.*`; the example files are allowed), even when it changes nothing else. Take it out with `git rm --cached <file>`, and change any password it held: git history keeps it.
- **`ship.json` can't loosen its own check:** moving the backend or frontend folder counts as code; the `bookkeeping` list may never cover the code folders, and a change to it counts only from the next push.
- **Push to `main`:** every piece has the client's verdict (none building, none waiting on dev), the commit came through `dev`, and the check passed on it there. A release pushed right after the dev push waits up to 10 minutes for the dev check.

Claude Code runs the same rule before a push, starting from what is already on `dev`. A push from your own terminal or GitHub's website skips Claude Code, but it still can't deploy unchecked code: the check here fails and nothing deploys.

**The limit.** The check runs from files in this repo. It stops mistakes and hurried pushes, not someone who deliberately edits this folder or the workflow to switch it off. Only GitHub's branch rules close that, and on a private repo they need a paid plan.

## Your devops

Your deploy must start only after the Ship check passes on that commit. In GitHub Actions, run it from the check's result:

```yaml
name: Deploy
on:
  workflow_run:
    workflows: ["Ship check"]
    types: [completed]
    branches: [dev, main]
jobs:
  deploy:
    if: >-
      github.event.workflow_run.conclusion == 'success' &&
      github.event.workflow_run.event == 'push' &&
      startsWith(github.event.workflow_run.path, '.github/workflows/ship-check.yml')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.workflow_run.head_sha }}
      # Deploy here: github.event.workflow_run.head_branch is dev (→ the dev server) or main (→ live).
```

GitHub runs a `workflow_run` workflow only when its file is on the repo's default branch, so commit it there. The `path` line makes sure only the kit's workflow counts, not another one that borrows its name.

If the deploy doesn't run in GitHub Actions (the server pulls, or another tool deploys), it must ask GitHub first:
`GET /repos/<owner>/<repo>/actions/runs?head_sha=<sha>&branch=<dev or main>&event=push`
Take the newest run whose `path` is `.github/workflows/ship-check.yml`, and deploy only when its `conclusion` is `success`.

What every deploy must end with, whoever builds it:

- a dev link (from `dev`) and a live link (from `main`), written in the project page's Facts;
- nothing deploys unless the Ship check passed;
- dev and live use separate databases;
- daily backups kept off the server, and a restore tested at least once;
- a backup before every migration;
- rollback is one command, and was rehearsed;
- an alert when live goes down;
- secrets live in the server's environment, never in the repo.

These are the guide's release floor (step 8), plus the two links and the check.

## Cloudflare

The app runs on Cloudflare and its Postgres on Neon. One Worker per environment serves the built frontend and passes `/api/*` to the FastAPI backend, which runs in a Cloudflare Container built from the backend folder. App and API share one address. `dev` deploys to the Worker `<app>-dev`, whose link is the project page's Dev URL; `main` deploys to `<app>`, whose link is the Live URL.

Setup copied the deploy files once: `deploy/` (the Worker, the Container's Dockerfile, the Cloudflare config) and `.github/workflows/deploy.yml`. Unlike the files in `.github/ship/`, they are this project's own: change them through a piece, and setup never overwrites them. The workflow deploys a branch only after the Ship check passed on that commit. Never deploy by hand.

One-time setup (owner):

1. **Cloudflare:** the Workers Paid plan ($5 a month, by card; Containers need it). Note the account ID and your `workers.dev` subdomain (Workers & Pages → your subdomain).
2. **Cloudflare API token:** My Profile → API Tokens → Create Token → the "Edit Cloudflare Workers" template, scoped to this account. If the first deploy says the token can't push the container image, add the Containers permission the error names.
3. **Neon:** create one project with two databases or branches, one for dev and one for production, and copy each connection string. Never point dev at production's database.
4. **GitHub:** repo → Settings → Environments. Make two environments, `dev` and `production`. In each:
   - secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DATABASE_URL` (that environment's Neon string), and any other secret the backend reads;
   - variable: `APP_URL`, the environment's link (`https://<app>-dev.<your-subdomain>.workers.dev` for dev).
   Every secret of the environment reaches the backend as an environment variable of the same name, so a new secret needs no change to the deploy files.
5. Push to `dev`. When the Ship check is green, the Deploy job runs; open the app only when Deploy is green too, because the secrets go in after the Worker is up. Write the two links as the Dev URL and the Live URL in the project page's Facts.

The floor on this track:

- **Backups.** Neon's restore history lives inside Neon and is short on the free plan, so it is not the floor's "daily backups kept off the server". Until the kit ships a daily dump, take one yourself (ask Claude for a scheduled `pg_dump` to a bucket outside Neon) and restore it once into a scratch database to prove it works.
- **Before every migration:** make a Neon branch of the production database, or run the dump once by hand. Migrations run when the backend container starts.
- **Rollback:** in `deploy/`, `npx wrangler rollback --env production` returns the Worker and its container to the previous version in one command; it doesn't touch the database. Rehearse it once on dev.
- **Alerts:** Cloudflare doesn't watch whether the Live URL answers. Add an outside uptime check on it (ask Claude for a free one).
- **Secrets** live in the GitHub environments, never in the repo. For local runs put test values in `deploy/.dev.vars`, which git ignores.

Proven so far on one project, and on `dev` only: the `main` → production half of the workflow has not run yet. Treat the first release as a test and watch it.

To run it locally (needs Docker): in `deploy/`, `npm install`, build the frontend, then `npx wrangler dev --env dev`.
