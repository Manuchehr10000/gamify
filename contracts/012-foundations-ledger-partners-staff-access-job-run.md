# Contract: Foundations: ledger, partners, staff access, job runner
Status: on-dev
Base: 1acec1e125
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be608138b830c2088d0d536c

CHANGE to: 001, 002, 004, 006
Owner's words (TAG): «pieces 13–22 rely on four shared parts. Build these first.», from chat spec agreed 2026-11-02 by Manu

## What users see

- Points and coins record:
  - Every change to a guest's points or coins writes exactly one score_events row: task award (QR, link, market, photo, text, quiz), moderator bonus, «Отклонить — переснять», «Отклонить со штрафом», market purchase, login +10. Nothing bypasses it.
  - Each row also carries: base points, multiplier (default 1), the stage running when it was written, and the action it came from (arrival, task, bonus, retake, penalty, buy, speed, badge, withdraw).
  - Each guest has stored point and coin totals, updated in the same transaction as the row. Guests see the same numbers as before.
  - The admin gets «Проверить баланс» on /admin/live. It lists guests whose stored totals differ from the sum of their events (name, stored, sum), or «Расхождений нет». It changes nothing.
- Partners table:
  - A new partners table: name, package (General, Headliner, MF Partner, Supporters), logo (empty until pieces 13/18), active.
  - The migration builds it from the partner names already in tasks and prizes. Each upload of the «Задания» and «Призы» sheets matches partners by name, and a new name creates a partner.
  - Tasks and prizes link to a partner by ID. The Excel sheets keep their «Партнёр» / «Пакет партнёра» columns, and export writes them back from the partner.
  - Package order in the feed, the partner ×1.5 coin rule, «Друг бренда» and the partner report keep working as now, keyed by partner ID.
- Staff access:
  - The desk PIN, stand PIN, moderator names and PINs, and admin password move from environment settings into the database, stored hashed (bcrypt).
  - Four roles: admin, moderator, desk, stand. Admins have named accounts. The first admin, «Администратор», is created from today's password, and the old password logs in as that admin.
  - The login screens stay as they are: a PIN or password alone identifies the account (each one unique).
  - Sessions record which staff account is acting, so later logs name the admin or moderator.
  - Every staff endpoint checks the role on the server. Moderators are also allowed the hall screen switches that piece 18 adds.
- Job runner:
  - One Cloudflare scheduled trigger runs every minute and calls the backend, which runs each registered job in turn. Pieces 14, 19 and 22 register: lapsed claims, push sending, photo deletion.
  - Each run of each job is logged with its start, end and result (ok, or the error).

## Rules

- score_events is append-only: no row is edited or deleted. «Отклонить — переснять» adds a reversal row that points at the award it reverses and takes the award's points and coins back, instead of deleting the award. The task reopens, and a new submission is awarded afresh. Feed, badges, moderation queue, quiz and the live/partner counts treat an award with a reversal row as not done.
- A negative take-back row with no reverses_id (penalty, withdraw) is not a reversal: the award still counts as done. 'Done' here means the task stays closed for that guest; /admin/live and the partner CSV still leave out penalized submissions as 010 does.
- One open award per guest per reason: the ledger helper checks this under the guest's row lock, replacing the current unique (guest_id, reason) constraint, so a double scan or a second phone still adds nothing.
- Points on a row = base points × multiplier, rounded to whole points, halves up (see piece 16). The multiplier is always 1 until piece 16 sets it. The migration backfills base points = points and multiplier = 1 on existing rows.
- action values are arrival, task, bonus, retake, penalty, buy, speed (piece 17), badge (piece 20, its award and its reversal), withdraw (piece 22).
- All writes go through one ledger helper that inserts the row and updates the totals in one transaction. The market's coin check reads the stored total under the existing guest lock.
- A partner's package comes from the «Задания» sheet. Two task rows naming one partner with different packages make the row fail with a Russian reason. The «Призы» sheet only matches or creates by name (a new partner from prizes gets no package).
- Staff secrets are seeded once from the current environment values (DESK_PIN, STAND_PIN, MODERATORS, ADMIN_PASSWORD) when the staff table is empty. After that the environment values are ignored. They are removed from deploy/ and .env.example only in a follow-up commit, after the seeding deploy has run on dev and production.
- Role checks live in require_role / current_moderator and router-level dependencies=; existing @router... decorator lines are left byte-identical.
- The job endpoint takes only the Worker's shared secret (JOBS_SECRET, in environment files). The Worker's public fetch refuses /api/jobs/*, so only the scheduled trigger reaches it.
- Runs don't overlap: if the previous run still holds the lock, the new run is logged as skipped. One failing job is logged as failed and the other jobs still run.

## What's out

- Forms to add or edit partners, logos, staff accounts, PINs or passwords, and the change log of moving a task to another partner (piece 13)
- Uploading logos or showing them anywhere (pieces 13, 18)
- The hall screen switches themselves (piece 18). This piece only gives moderators the role permission.
- The jobs themselves: push sending (19), lapsed claims (14), photo deletion (22). This piece ships only the runner and its registry.
- Any multiplier other than 1 (16), and the blitz speed bonus (17)
- A screen for reading the job log (it lives in the job_runs table and the Worker logs)
- Fixing a mismatch from «Проверить баланс»: it only reports
- Admin login by name + password, password reset, lockout after wrong tries
- Per-partner stand PINs (still one shared stand PIN)
- Moving existing quiz settling (now done on request) into the job runner
- Rewriting past retakes: awards deleted by «переснять» before this piece stay deleted; no reversal rows are backfilled for them

## How to check it

- When a moderator gives a bonus, rejects, or a guest buys, then score_events gets one row and the totals match it.
- When I run «Проверить баланс» on clean data, then it lists nobody; after I edit a total by hand in the database, it lists that guest.
- When I upload the tasks file with a new partner name, then a partner is created and its tasks link to it.
- When a moderator calls an admin action directly, then the server refuses it.
- When I log in with the old admin password after migration, then it works as the first named admin.
- When two test jobs are registered and POST /api/jobs/run is called with JOBS_SECRET, then job_runs holds one ok row per job.
- (added) When a moderator presses «Отклонить — переснять», then the award row stays, a new row takes its points and coins back, and the guest can send the task again and be paid once more.
- (added) When a guest scans the same QR twice after the unique constraint is replaced, then only one award row is written.
- (added) When I log in at /desk, /stand/{code} and /moderate with the PINs from before the migration, then each works, and the database holds only their hashes.
- (added) When I download the tasks file after the migration, then «Партнёр» and «Пакет партнёра» show the same values as before.
- (added) When the first of two test jobs raises, then job_runs shows its error and the second still runs and logs ok.
- (added) When a run starts while the previous one holds the lock, then it is logged as skipped.
- (added) When a moderator rejects with a penalty, then /admin/live's completions drop by one, as before.
- (added) When I call POST /api/jobs/run from outside without the secret, then it is refused.

## Size

Screens: 0

Endpoints: 2

- GET /api/admin/balance-check
- POST /api/jobs/run

Tables: 3

- partners
- staff
- job_runs

## Decisions

- Open item: Does score_events already cover coins as well as points? → Decision: Yes, read from the code. It has a coins column, and the market purchase (coins −price), bonus, penalty, quiz, task and login +10 all write it. Two gaps to fix: (1) «переснять» deletes the award row and writes none, which fails the agreed check «rejects … score_events gets one row», so it becomes a reversal row (Rules); (2) there are no stored totals (totals are summed on every read), so guests gets points/coins columns updated in the same transaction. Piece 13's inventory doesn't need to answer this first.
- Open item: Confirm Cloudflare scheduled triggers reach the backend container. → Decision: They can. The Worker's scheduled() handler calls getContainer(env.BACKEND).fetch() on POST /api/jobs/run with JOBS_SECRET, the same way fetch() does today; the cron goes in triggers.crons per env in wrangler.jsonc.
- Open item (from code): a cron every minute keeps the container from sleeping (sleepAfter 2h), so it runs all day, every day. → Needs Manu: accept always-on container cost on dev and production, assumed every-minute cron on both meanwhile.
- Open item (from code): there is no /admin page to hold «Проверить баланс». → Decision: put it on /admin/live, the existing admin overview, so no new screen. Piece 13 may move it into its settings area.
- Open item (from code): how named admins log in without changing three login prompts. → Decision: the password alone identifies the admin, as moderator PINs already do. Passwords must be unique, enforced when piece 13 adds accounts.
- Open item (from code): where the staff seed comes from. → Decision: a one-time seed from the current environment values when the staff table is empty. This keeps the old admin password and PINs working without anyone retyping them. The env values leave deploy/ and .env.example only after the seed has run on both environments, so production never boots with no admin.
- Open item (from code): the action on each row. → Decision: an explicit action column (arrival, task, bonus, retake, penalty, buy, speed, badge, withdraw) next to the existing reason, and existing rows are backfilled from reason in the migration. speed, badge and withdraw are added now so pieces 17, 20 and 22 need no change to the column.
- Open item (from code): score_events has UniqueConstraint(guest_id, reason), and task awards, quiz and login +10 rely on it via on_conflict_do_nothing to ignore double scans; every done check (feed task_reason(id) in done, moderation queue join, badges, live counts, quiz) matches reason == "task:{id}". Keeping the award row and re-awarding with the same reason would break the constraint. → Decision: drop the unique constraint; a reversal row carries reverses_id (unique, FK to the award); the ledger helper, under the guest's row lock, writes an award only when no unreversed row with that reason exists; done = an award row with no reversal pointing at it. Reason strings stay task:{id}, so exports and reports keep their keys.
- Open item (from code): which sheet sets a partner's package, and what happens on conflicting packages. → Decision: «Задания» sets it (only it has «Пакет партнёра»); conflicting packages for one partner fail that row with a Russian reason; «Призы» only matches or creates by name, with no package.
- Open item (from code): making every staff endpoint check its role could edit decorator lines (/api/admin/rating/freeze, /api/submissions/{submission_id}/photo carry inline dependencies), which the size check would count as new endpoints. → Decision: put role logic inside require_role / current_moderator and router-level dependencies=; leave decorator lines unchanged.
- Stack: no new packages. bcrypt, sqlalchemy, alembic and @cloudflare/containers are already in ship.json.
