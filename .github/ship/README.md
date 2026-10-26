# Ship: how this project deploys

Written by `/ship:setup` from the Ship kit. Don't edit the files in this folder or `.github/workflows/ship-check.yml`: rerun `/ship:setup` to update them.

## What runs on every push

GitHub runs the **Ship check** (`.github/workflows/ship-check.yml`, using the copy of the kit's script in this folder) on every push to `dev`, `main` and `master`. Nothing may deploy unless it passes.

- **Push to `dev`:** a push that changes only bookkeeping (contracts, `ship.json`, `CLAUDE.md`, `.gitignore`, `.github/`, the readme) passes. Any product code needs the piece that is building to pass the CTO check (size, stack, leftovers), and it must come after that piece was picked up. The check starts from the newest commit it passed on, so a failed push can't hide under a later one.
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

## Railway

Railway's names for the two branches: `dev` deploys to an environment called **staging**, whose link is the project page's Dev URL; `main` deploys to **production**, whose link is the Live URL.

1. In Railway, create a project from this GitHub repo. Make one service per folder (the backend and the frontend), each with its folder as the root directory.
2. The production environment deploys from `main`: set each service's trigger branch to `main`.
3. Add an environment named `staging` that deploys from `dev`: set each service's trigger branch there to `dev`.
4. In every service, in both environments, turn on **Wait for CI**. Railway then waits for the Ship check and skips the deploy when it fails. Railway waits for whatever workflows the commit has, so it can't tell if the check's files were removed; that's the limit above.
5. Add a Postgres database in each environment. Never point staging at production's database.
6. Daily copies off the project. Railway's own backups and point-in-time restore live inside the project, so a deleted project or a wiped volume takes them along. Add Railway's "Postgres S3 backups" template as a service in production, pointed at production's database and at a storage bucket in a separate Railway project; it dumps once a day by default. Turn Railway's daily backups on as well: they're the quick restore. Once, restore the newest dump into a scratch database to prove it works.
7. Before every migration, take a manual backup in the database's Backups tab, or run the dump service once by hand.
8. Rollback: on the service's Deployments tab, the three dots on an earlier deploy → Rollback. It restores that deploy's image and variables in seconds, not the database; a migration needs step 7's backup. Rehearse it once on staging. The Hobby plan keeps old images for 72 hours.
9. Alerts: in the project's Settings → Webhooks, paste a Slack or Discord webhook; Railway then reports a failed or crashed deploy. It doesn't watch whether the live link answers, so add an outside uptime check on the Live URL (ask Claude for a free one).
10. Put secrets in Railway's variables, never in the repo. Write the staging link as the Dev URL and the production link as the Live URL in the project page's Facts.

Railway bills by use and needs a card: the Hobby plan is $5 a month and includes $5 of use. Check that your card pays it before you rely on it.

## Cloudflare

Not ready yet: the kit still needs its TypeScript stack list, size counts and deploy step. Setup stops on this track until they land.
