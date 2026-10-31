# Contract: Badge login
Status: on-dev
Base: 3695850925
Approved: 2026-10-26 by Manu
Tracker: https://app.notion.com/p/405c62b4be60812bb2efc062c4c7d382

Client's words (TAG): «Вход через сканирование QR-кода на бейдже участника (камера устройства); QR кодирует ID регистрации форума. Резервный вход — по номеру телефона + код формы регистрации (для случая, если бейдж не считался). Без пароля и email — упрощённая идентификация, чтобы не терять «пробующих» игроков на первом шаге. После входа — экран приветствия и сразу одна лёгкая задача (не форма), чтобы участник получил первые баллы в первую минуту.», from backlog, added 2026-10-26

## What users see

- A guest scans their badge QR with the phone camera; the app opens with them logged in.
- On first visit: one consent line (first name and last initial shown in the rating; moderators see your photos; photos deleted 30 days after the forum) and an OK button.
- Then a welcome screen with their first name and "+10 for coming to the forum".
- Next visits open the app logged in, with no second +10.
- A wrong or broken link shows "Бейдж не найден — подойдите к стойке регистрации".
- Desk staff enter a PIN on /desk, find a guest by name or phone, and show that guest's QR on the tablet to scan; they can add a walk-in (name, phone, company) and get a QR for them.
- The admin enters a password on /admin/guests, uploads TAG's guest list, and downloads it back with a link column for badge printing.
- Uploading the list again keeps every existing guest's link and gives links only to new guests.
- All texts are in Russian, kept in one language file.

## What's out

- Guests logging in by phone on their own; SMS codes
- Blocking one badge on two phones
- The task feed: the welcome screen's "К заданиям" button leads to an empty page until piece 2
- Any points beyond the login +10; levels; profile
- Editing or deleting a guest by hand (re-upload instead)
- Tajik texts; the job that deletes photos after 30 days
- Setting up the event subdomain
- Per-person staff accounts: one shared desk PIN and one admin password, kept in the GitHub dev environment and passed to Cloudflare on deploy

## How to check it

- When I upload TAG's guest list (UTF-8 or saved from Excel, Cyrillic names) on /admin/guests, then I see how many guests were added and which rows failed, and why.
- When I download the list, then every guest has a link with a unique random code, not their registration ID.
- When I upload the same list again with two new guests, then the old links stay the same and only the two new guests get links.
- When I open a guest's link on a phone for the first time, then I see the consent line, and after OK I see the welcome screen with their first name and +10.
- When I open the same link again, then I am logged in and the +10 is not added again.
- When I open the link on a second phone, then I am logged in as the same guest.
- When I change one character in the code, then I see "Бейдж не найден — подойдите к стойке регистрации".
- When I enter the desk PIN, search a guest by phone and scan the QR on the tablet, then that phone is logged in as that guest.
- When I add a walk-in at the desk, then a QR appears, and scanning it logs them in with the welcome screen and +10.
- When I open /desk or /admin/guests without the PIN or password, then I see only the login prompt.
- When I open the language file, then I see every text from these screens.

## Size

Screens: 3

- /app/welcome
- /desk
- /admin/guests

Endpoints: 8

- GET /b/{code}
- GET /api/me
- POST /api/consent
- POST /api/staff/login
- POST /api/admin/guests/import
- GET /api/admin/guests/export
- GET /api/desk/guests
- POST /api/desk/guests

Tables: 3

- guests
- sessions
- score_events
