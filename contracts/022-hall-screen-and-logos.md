# Contract: Hall screen «Эфир» and logos
Status: building
Base: 2566eb635c
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40cc62b4be608134a5dfc2ae9e5a71d5

CHANGE to: 007
Owner's words (TAG): «В последние 30 минут этапа 4 — отдельный режим «эфир»: полноэкранный топ-10 с автообновлением, предназначен для трансляции на большом экране в зале.», from chat spec agreed 2026-11-02 by Manu

Client's words (TAG): «…топ-10 лидерборда, обновление раз в 10–15 секунд, брендирование форума и партнёров, для вывода через HDMI/проектор на экран в зале.», from piece 7

## What users see

- On /hall (still no login, read-only, as 007), outside «Эфир» the screen cycles slides of about 8 seconds each:
  - the top 10 (as 007, with levels and badges)
  - partner logos
  - a countdown to the next event: the next quiz window («Доступно с» in 008), the market opening (first stage marked «Маркет»), or the next stage start, whichever comes first. With nothing ahead, this slide is skipped.
- Every push (piece 19) also shows its text full screen for 15 seconds, interrupting the cycle, then the cycle carries on.
- In the last 30 minutes of the last stage, /hall switches by itself to «Эфир»: full-screen top 10 with the forum's branding, refreshing every 10 seconds, with no other slides.
- Logos come from the partners table (piece 12), active partners only, with images read from piece 13's GET /api/partners/{id}/logo. A bigger package shows larger and more often (General > Headliner > MF Partner > Supporters).
- The 007 freeze still works in every mode: the top 10 slide and «Эфир» show the frozen places with «Итоги зафиксированы».
- Moderators (in /moderate) and admins (in /admin/live) see a «Экран в зале» panel with four switches and the current mode highlighted:
  - «Авто» (default): the cycle, with «Эфир» switching on by itself at its time
  - «Эфир сейчас»: «Эфир» at once, whatever the time
  - «Только логотипы»: only logo slides
  - «Пауза»: the screen holds the slide it is showing now
- A switch reaches the screen within 10 seconds (its next poll).

## Rules

- The screen loads the next slide's images before showing it. A logo that fails to load is left out of that slide; a slide with no loaded logos is skipped.
- If the network drops, the screen keeps cycling what it has (last top 10, logos already loaded, the countdown from its own clock) and recovers on its own, as 007.
- Each time a logo shows, the screen logs the partner, start time and seconds shown, for piece 21. Logs made while offline are kept on the screen and sent when the network returns.
- The server accepts a logo log only for an active partner, with seconds between 1 and 30 and a start time within the last 2 hours; anything else is dropped.
- «Эфир» starts at the last stage's end time minus the «Эфир» setting, read from the stages table each poll, so moving the last stage (or «Следующий этап») moves «Эфир» with it. After the last stage ends, «Эфир» stays on until a moderator or admin switches.
- Only moderators and admins can change the mode; the server checks the existing moderator or admin session on every call.
- Layout for 1920×1080; no text smaller than the minimum font size setting.

## Settings (piece 13)

- This piece registers its own keys and limits in piece 13's settings store and form registry:
- slide time (4–30 s, default 8), «Эфир» start (minutes before the end of the last stage, default 30), size and frequency per package, minimum font size (default 40 px): from now on
- Package defaults until an admin changes them: General large, on every logo slide; Headliner medium, every slide; MF Partner medium, every 2nd logo slide; Supporters small, every 3rd logo slide.

## What's out

- Guests' photos on the hall screen
- A blitz show
- Different content per screen: every screen open on /hall shows the same mode and slides
- Pushes interrupting «Эфир» or «Пауза»: they interrupt «Авто» and «Только логотипы» only
- Sending, scheduling or writing push texts (piece 19); this piece only shows on /hall the push piece 19 marks as sent
- Uploading, editing or serving partner logos (pieces 12 and 13; images come from piece 13's GET /api/partners/{id}/logo)
- A partners table or settings store of its own: both come from pieces 12 and 13
- The partner report and any view of the logo log (piece 21); this piece only records it
- A separate screen for the switches: they are a panel in /moderate and /admin/live
- A forum logo image beyond the forum name and colours, until TAG sends the file (see Decisions)
- Sound, video, animations between slides beyond a simple fade

## How to check it

- When the last stage has 30 minutes left, then /hall switches to «Эфир» by itself.
- When a moderator presses «Только логотипы», then only logos show until «Авто».
- When the push field in GET /api/hall is filled (in a test), then /hall shows its text full screen for 15 seconds, once per push id, in «Авто» and «Только логотипы» but not in «Эфир» or «Пауза».
- When the ranking is frozen, then every mode shows the frozen places.
- When I pull the network for 2 minutes, then the screen keeps cycling and recovers.
- When a General partner and a Supporter are both active, then the General logo shows larger and more often, and both appear in the logo log.
- When I stand 20 metres from the real screen, then I can read every line.
- (added) When the next quiz opens at 14:00 and it is 13:50, then the countdown slide shows 10 minutes to that quiz.
- (added) When a moderator presses «Эфир сейчас» at any time, then /hall shows «Эфир» within 10 seconds; «Авто» returns it to the cycle.
- (added) When a moderator presses «Пауза», then the screen holds its current slide until another switch.
- (added) When an admin opens /admin/live, then the «Экран в зале» panel shows the current mode highlighted, and a switch pressed there reaches /hall within 10 seconds.
- (added) When a guest or a logged-out browser calls the mode switch directly, then the server refuses it.

## Size

Screens: 0

Endpoints: 2

- POST /api/hall/mode
- POST /api/hall/logo-shows

Tables: 2

- hall_state
- logo_shows

## Decisions

- Open item: From TAG: how many screens, and their size. → Needs Manu: confirm with TAG the number of screens and their resolution, assumed one or more 1920×1080 screens all showing the same /hall meanwhile.
- Open item (found while reviewing): this piece needs the partners table (piece 12) and Piece 13: settings store and form registry, and neither exists in the code yet. → Decision: pick this piece up only after 12 and 13 are done; it builds no partners or settings table of its own and registers its own settings keys and limits in 13's store and form, so Tables stays at 2.
- Open item (found while drafting): where the four switches live. → Decision: a «Экран в зале» panel in /moderate and /admin/live, not a new route, so Screens stays 0 and both roles use pages they already log into.
- Open item (found while drafting): who may switch. → Decision: the existing moderator session (POST /api/moderator/login) and admin session (require_role("admin")), with no new staff login.
- Open item (found while drafting): where the mode is stored. → Decision: a one-row hall_state table (mode, changed by, changed at), not piece 13's settings store, because the mode is live state flipped many times a day and shouldn't fill the settings change log or follow its effect rules.
- Open item (found while drafting): what «Пауза» freezes when several screens are open. → Decision: each screen holds whatever slide it is showing when it sees «Пауза»; the server stores only the mode, so no slide index has to be synced.
- Open item (found while drafting): does a push interrupt «Эфир»? → Decision: no, «Эфир» is "no other slides" and «Пауза» is a hold; pushes interrupt «Авто» and «Только логотипы» only.
- Open item (found while drafting): how the screen gets the push. → Decision: GET /api/hall (existing, body extended) also returns mode, slide settings, active partners with logo URLs (piece 13's GET /api/partners/{id}/logo), the next countdown target, and a push field: the latest push sent in the last 15 seconds (with its id, so a screen shows each push once). This piece owns the push field; it stays null until piece 19 fills it, so this piece's push check fills the field in a test, and the check with a real sent push belongs to piece 19.
- Open item (found while drafting): logo log endpoint needs no login like /hall, so it can be spammed. → Decision: server-side checks (active partner, 1–30 s, start within 2 h) instead of a screen login, keeping 007's "no login" promise; piece 21 can flag outliers.
- Open item (found while drafting): what "the forum's branding" means. → Needs Manu: ask TAG for the forum logo file (SVG/PNG), assumed forum name from the language file and the forum's colours meanwhile; the file, when it comes, goes in as a static asset, not demo data.
- Open item (found while drafting): what happens after the last stage ends. → Decision: «Эфир» stays on until a moderator or admin switches, since the closing ceremony follows and the frozen top 10 should stay up.
- Open item (found while drafting): package size and frequency defaults. → Decision: General large every logo slide, Headliner medium every slide, MF Partner medium every 2nd, Supporters small every 3rd; admins change them in piece 13.
- No new packages: preloading uses the browser's Image, offline logs use the existing try/catch localStorage pattern, the fade uses CSS.
