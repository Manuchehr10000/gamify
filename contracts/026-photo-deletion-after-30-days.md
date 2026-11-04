# Contract: Photo deletion after 30 days
Status: on-dev
Base: 2435c4ecd2
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be60813fbfb2c684ffc79bf4

CHANGE to: 001, 005
Owner's words (TAG): "The promise, from the consent screen in piece 1: photos are deleted 30 days after the forum.", from chat spec agreed 2026-11-02 by Manu

## What users see

- A guest can delete their own photo from the task card (/app/tasks/{id}) or from /app/profile, with a confirmation.
  - If the moderator has accepted it («Принять» or «Бонус»): the photo goes, the points and coins stay.
  - If it is still undecided: the submission is withdrawn, its points and coins are taken back, and its place in the task's limit frees. The confirmation says so.
  - If the moderator rejected it (retake or penalty): the photo goes and nothing else changes.
- After withdrawing, the card leaves the rotation like a done task and /app/tasks/{id} shows «Фото удалено — задание снято» in place of a state label, with no fifth state, the same treatment piece 15 gives a penalty.
- Seven days before the deletion date, admins see a banner on the admin pages: «1 240 фото будут удалены 15 января» (live count and date).

## Rules

- One deletion date: the photo deletion date key piece 21 registers in piece 13's settings store, with piece 21's shared helper giving the default (the local date of the last stage's end, in event time UTC+5, + 30 days). This piece reuses that key and helper and does not define its own.
- On that date, the job runner (piece 12) deletes every photo and thumbnail in batches, empties the photo on each submission, then compacts the table so the space is freed.
- Submissions, texts, points and score_events stay.
- The job logs the count, start and end time, and the date Neon's restore history stops holding the photos (end time + the restore-history length). That last date is when the promise is fully kept.
- The job is safe to stop and rerun: a rerun continues with whatever photos remain; the compaction and the final log entry happen once, after the last batch.
- Withdrawing writes a negative take-back row in score_events (points and coins back) with action withdraw and no reverses_id, like a penalty, so under piece 12 the award still counts as done and the task stays closed for that guest (one submission per task, 005). Piece 12 lists withdraw among the action values. The new submission status withdrawn fits the existing column.
- After a withdrawal, the level and badges follow as after a penalty (009, 011), and coins may go below zero if they were already spent.
- The submission status withdrawn keeps it out of the moderator queue (it is no longer undecided), the badges and piece 15's places-used count for the task's limit.
- A withdrawn submission is left out of completions() (so out of both /admin/live and piece 21's report, completions and unique guests), the same as a penalty, and is not counted in the rejected column.
- A guest's delete is checked on the server against the submission's status at that moment, under a row lock, so a moderator deciding during the confirmation can't be lost.
- Once the photos are gone, every photo link (moderator view, partner report from piece 21) answers «not found».

## Settings (piece 13)

- photo deletion date (key and default helper from piece 21): this piece adds only the rule that it is locked once the 7-day banner shows

## What's out

- Showing the guest their own photo (the card and profile show only a «Удалить фото» action, not the image)
- Re-sending a task after withdrawing it
- Deleting texts, submissions, guests or score_events
- A per-guest or per-task deletion date; deleting photos earlier than the one date by an admin button
- Reading Neon's restore-history length from the Neon API (it comes from configuration)
- Telling guests by push or message when photos are deleted (piece 19 owns pushes)
- The job runner itself, its schedule and its run log (piece 12); the settings form and lock mechanics (piece 13); thumbnails (piece 14); task limits and card states (piece 15); partner report links, the photo deletion date key and its default helper (piece 21)
- Checking TAG's rules document wording (owner's task, see Decisions)

## How to check it

- When I delete an accepted photo, then it's gone and my points stay.
- When I delete an undecided photo, then my points and coins drop and the task's place frees.
- When the date is 7 days away, then admins see the count.
- When the job runs on a copy of the database, then no photos remain, the database shrinks, and the log shows the count and the restore-history date.
- When the job has run, then every partner report photo link stops working.
- When I press delete and then cancel the confirmation, then nothing changes. (added)
- When I delete the photo of a rejected submission, then it's gone and my points and coins don't change. (added)
- When I withdraw an undecided photo, then /admin/live and the partner file both drop that completion and still match.
- When I withdraw an undecided photo, then its card no longer shows «На проверке» and does not come back in the batch.

## Size

Screens: 0

Endpoints: 2

- DELETE /api/submissions/{id}/photo
- GET /api/admin/photo-deletion

Tables: 0

## Decisions

- Open item: Manu: check the Neon plan's storage limit and restore-history length. → Needs Manu: the Neon plan's storage limit and restore-history (point-in-time restore) length, assumed 7 days meanwhile, kept as an environment value (infrastructure, not a game setting) so the log's "promise fully kept" date is right once he confirms; if storage is tight before the date, piece 14's 1 MB / 100 KB caps are the lever.
- Open item: Check that TAG's rules doc promises the same as the consent screen. → Needs Manu: confirm with TAG that their rules document says "deleted 30 days after the forum", assumed it matches the consent screen meanwhile; if TAG's text differs, the deletion date setting covers it without code changes.
- Open item (from the code): which photos a guest may delete. → Decision: all their own photos, as the spec's "their own photo" says; a rejected one just loses its photo (its points were already settled by the moderator), the same path as an accepted one.
- Open item (from the code): what a withdrawal does to the task. → Decision: a negative take-back row in score_events with action withdraw and no reverses_id, like a penalty, so the award still counts as done under piece 12 and the task stays closed, keeping 005's one-submission rule; new submission status withdrawn (fits String(16), stays inside the unique guest/task index) keeps it out of the queue, the badges and 15's places-used count; no new table.
- Open item (from the code): where the banner's count comes from. → Decision: one admin endpoint returning date, photo count and locked flag, shown by a shared banner on the existing admin pages; no new screen. The guest's delete action uses the submission id, which /api/tasks/{id} and /api/profile return (body changes, not new endpoints).
- Open item (from the code): where the job's log lives. → Decision: in piece 12's run log as the job's result (count, start, end, restore-history date); no new table.
- Open item (from the code): compaction. → Decision: VACUUM FULL submissions run outside a transaction after the last batch; it holds an exclusive lock on the table for the whole rewrite and needs free space about the size of the remaining table, acceptable 30 days after the forum; "the database shrinks" is measured by pg_database_size, since Neon's billed storage keeps old pages until the restore-history window passes.
