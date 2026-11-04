# Contract: Skin choice for the event
Status: on-dev
Base: e5b78d5722
Approved: 2026-11-03 by Manu
Tracker: https://app.notion.com/p/40dc62b4be6081b49442f2a569c4c85d

CHANGE to: 23–26 (the Console look becomes one of four skins), 13 (adds one setting)
Needs: piece 13 (settings, log, GET /api/version) and pieces 23–26 (every screen in the design system's look)
Owner's words: «as an alternative theme selector build me 3 additional themes as skins on top of existing layout. We have Atari already. Add 1. Victorean Era Steampunck 2. Space oddessy 2001 3. Tajik national ornament», from chat 2026-11-02

Owner's words: «Skin choice», from chat 2026-11-03

Owner's words: «agree» (to the names, mid-game change and fonts below), from chat 2026-11-03

Design: Gamify Console design system, Skins card · every artboard on the guest, admin and staff and hall canvases has a Skin tweak

## What users see

- One event, one skin. In the «Настройки» tab of /admin/settings an admin picks the event's skin from four: «Консоль», «Стимпанк», «Космос», «Таджикский орнамент» (Console, Steampunk, Space age, Tajik ornament). Each choice shows a small preview of the same card in that skin. Default: Console.
- Each skin has two themes, and every page uses the one made for it:
  - Guest pages and /hall use the dark theme: Console, Brass, Orbit, Lapis.
  - /desk, /stand/:code, /moderate and every /admin page use the light theme: Label, Parchment, Station, Suzani.
- Saving asks for confirmation first («Оформление сменится на всех экранах: у гостей, на стойках и в зале»), as piece 13 does for live changes. After saving, every open phone, staff page and the hall screen switch within 10 seconds, with no reload by hand.
- Layout, words, buttons and behaviour are the same in every skin; only colours, fonts, corners, shadows and the drawn textures change.
- A page opens straight in the last skin it saw: no flash of Console first. With no network it keeps that skin.
- A page loads only its skin's fonts. Every skin's fonts show Russian and Tajik letters (ҳ, ҷ, ӣ, қ, ғ, ӯ).
- The change shows in the «Журнал» tab like any setting: admin, time, old skin, new skin.
- Effect rule shown beside the field: from now on. The skin can be changed at any time, also while the game is running; the confirmation is the guard.
- Fonts are files shipped with the app, not Google Fonts, so every skin's fonts work offline.

## Rules

- The skin is one key in piece 13's settings table, so it adds no table.
- GET /api/version (piece 13) also returns the skin id, so pages that already poll it learn the change with no new endpoint. /hall, the staff login pages and /app/welcome read it without a login.
- Pages set the theme with data-theme on the root, as the design system does; the design system's tokens, textures and fonts stay as published.
- All eight themes keep 4.5:1 text contrast (already checked in the design system).

## What's out

- Each guest choosing a skin; different skins on different screens or halls
- New skins, custom colours, or the client's own logo or brand colours
- A light theme for guests or a dark one for staff
- Changing the skin on a schedule (it changes when an admin saves)
- Any change to layout, copy or behaviour per skin

## How to check it

- When I open «Настройки» in /admin/settings, then I see the four skins, each with a preview, and Console chosen.
- When I pick «Стимпанк» and save, then I am asked to confirm, and nothing changes if I cancel.
- When I confirm «Стимпанк», then within 10 seconds a guest's /app shows the dark brass look, /hall shows the brass board, and /desk, /moderate and /admin/live show the light parchment look, without anyone reloading.
- When I open the «Журнал» tab after the change, then I see Console → Steampunk under my name.
- When I reload /app after the change, then it opens in the brass look straight away, with no Console flash.
- When I open /app with the network off after the change, then it still shows the brass look.
- When I open /app in the Tajik ornament skin, then Tajik words such as «Тоҷикӣ, ҳамаи ҷойҳо, қоидаҳо, ғолиб» show in the skin's own font, not a fallback.
- When I open /app in any skin and look at the network panel, then only that skin's fonts are loaded.
- When I open /app/welcome, /app, /market and /hall in each of the four skins at 320 px wide (1920 px for /hall), then nothing overlaps or scrolls sideways.

## Size

Screens: 0 (one field in the «Настройки» tab of /admin/settings, from piece 13)

Endpoints: 0 (GET /api/version gains a skin field)

Tables: 0 (one key in settings)

## Decided

- Skin names: «Консоль», «Стимпанк», «Космос», «Таджикский орнамент». They and the confirmation text are new ru.json keys.
- Skin changes are allowed while the game is running, with the confirmation.
- Fonts: files shipped with the app. Piece 23 must ship them the same way.
- Order: after 13 and 23–26, so it only switches screens that already use the design system.
