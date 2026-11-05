# Contract: Home address opens the guest app
Status: on-dev
Base: 4307cf23fb
Approved: 2026-11-04 by Manu
Tracker: https://app.notion.com/p/40ec62b4be6081f58fc3f0aefb8dd77e

Needs: piece 1 (badge login, /app/welcome) and piece 2 (/app feed and its signed-out message)
Owner's words: «page is empty» (about https://gamify-dev.manuchehr-407.workers.dev), from chat 2026-11-04

Owner's words: «Spec a home page», then chose «Send to /app», from chat 2026-11-04

Owner's words: «Approve the change» (Size: the catch-all route * counts as one screen), from chat 2026-11-04

## What users see

- Opening the bare address (/) no longer shows an empty page: it goes straight to /app.
- A guest who signed in through their badge link lands in their feed, as at /app.
- Anyone not signed in sees the existing message on /app: «Бейдж не найден — подойдите к стойке регистрации», in the event's skin.
- Back from /app does not return to the empty / (the address is replaced, not added to history).
- Any other address that matches no page also goes to /app instead of showing an empty page.

## What's out

- A new landing or welcome screen, event name, logo or text on /
- Links or buttons to staff pages (/admin, /desk, /market, /moderate, /hall, /stand) from / or /app
- Any change to the badge link (/b/…), /app/welcome or the /app signed-out message
- A production (Live) site or its address

## How to check it

- When I open / signed out, then I am at /app and see «Бейдж не найден — подойдите к стойке регистрации».
- When I open / after signing in through my badge link, then I see my feed at /app.
- When I open / and then press Back, then I do not land on an empty page.
- When I open /nothing-here, then I am at /app, not on an empty page.
- When I open /admin/guests, /desk and /hall directly, then they open as before.

## Size

Screens: 1 (the catch-all route redirects to the existing /app, no new page)

- `*`

Endpoints: 0

Tables: 0
