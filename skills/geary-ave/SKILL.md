---
name: geary-ave
description: Use when the user asks about Geary Ave Rehearsal Studios (gearyaverehearsal.com, Toronto) - whether a rehearsal room or studio is free, what times are available for a 2h/3h solo or band session, which studios are free or what gear a room has, or to book a studio and get the payment link.
---

# Geary Ave Rehearsal Studios

## Overview

The booking page is a Booknetic wizard whose every step is a plain HTTP call. `scripts/geary.py` makes those
calls directly: availability in about a second, no browser, no login. **Do not open the website in a browser**:
the widget has no accessibility roles, snapshots come back empty, and clicking through it takes 15 minutes to
learn what one command returns.

All commands: `python3 <skill dir>/scripts/geary.py <command> ...`. Times are Toronto local, 24h.

## Quick reference

| Question | Command |
|---|---|
| 3h solo slots in the next two weeks | `geary.py avail --hours 3` |
| ...ending by 5pm on a weekend | `geary.py avail --hours 3 --dow sat,sun --before 17:00` |
| 2h slots on Tuesdays | `geary.py avail --hours 2 --dow tue` |
| Is Studio 11 free Saturday | `geary.py avail --hours 3 --date 2026-09-19 --studio 11` |
| Evenings only | `--after 18:00` |
| A whole month | `--month 2026-10` |
| Which rooms are free for a slot | `geary.py studios --date 2026-09-19 --time 12:00 --hours 3` |
| What kit is in a room | `geary.py rooms --match "studio 11"` or `--match maple` |
| Price a booking (dry run) | `geary.py book --date D --time HH:MM --hours 3 --studio 11` |
| Book it | same command plus `--confirm` |
| Undo a booking that was never paid | `geary.py cancel-unpaid --payment-id ID` |

Add `--json` to any command for machine output.

## Rules that are not obvious

- **Hours change availability.** Always pass the length the user wants; a 2h list and a 3h list differ. Default
  to nothing: if the user did not say how long, ask (they usually book 2 or 3 hours).
- **`--type` defaults to `solo`**, which picks Weekday Solo or Weekend Solo from each date. Band rooms are
  `basic`, `standard`, `standard-plus`, `premium` (2h minimum). Only use those when the user says band or room tier.
- **`--before HH:MM` means the session ends at or before that time.** "Ending before 5pm" is `--before 17:00`, which
  includes the 14:00-17:00 slot. Say so in the answer if it matters.
- **Weekday solo is off-peak only:** 12:00-19:00 and 22:00-24:00. A weekday evening between 19:00 and 22:00 is not a
  gap in bookings, it is a rate rule; offer the 22:00 start or a band-rate room (`--type standard`) instead.
- **Studio 19 has no gear data** in the bundled list (it prints `?`); say so rather than guessing its kit.
- **A slot is one start time.** The site offers hourly starts; the end is start plus hours. Report as `12:00-15:00`.
- **Free studios are per slot.** `avail` without `--studio` means at least one room is free. Run `studios` to see which.
  Staff id equals studio number.
- **Booking is two steps.** Run `book` without `--confirm` first and show the price line; only add `--confirm` for a
  slot, length, and studio the user explicitly named. `--confirm` creates the appointment and prints a Stripe link
  that expires: hand it over immediately. Only the $1 deposit is paid online.
- **Every confirmed booking goes on the calendar, built from the script, not the site.** Right after `--confirm`
  succeeds, create a Google Calendar event: title `Rehearsal — Geary Ave Studio <N>`, start and end from the
  `CALENDAR:` line (`start_iso`/`end_iso` in `--json`), timezone `America/Toronto`, location
  `330 Geary Ave, Toronto ON M6H 2C7`. Put the rate type, length, room kit, appointment number, price, and the
  cancellation policy in the description. Never use the confirmation's Google Calendar or iCal links: they stamp
  Toronto local time as UTC and the event lands 4 hours early. This is part of booking, not an extra the user has
  to ask for; mention it in the same reply as the payment link.
- **Keep the ids.** Put `appointment_id` and `payment_id` in the reply and the event description. An unpaid deposit
  lapses on its own when the link expires; run `cancel-unpaid --payment-id` only when the user says to drop the booking.
- **Booking needs the site to know the user.** The script reads `PHONE=` from `~/.config/secrets.env` (override with
  `GEARY_SECRETS`) and looks the customer up. `CUSTOMER_NOT_FOUND` means stop and tell the user; never create a new
  customer record or pass the number on a command line. Never print the phone or anything else from that file.
- **Exit codes:** 0 ok, 1 error (message on stderr), 2 slot or studio unavailable (the message lists what is free).

## Common mistakes

| Mistake | Fix |
|---|---|
| Opening the booking page with agent-browser | Use `geary.py`; the widget is not snapshot-friendly and the API needs no browser |
| Listing 2h slots when the user asked for 3h | Pass `--hours 3`; the two lists are different |
| Answering "weekend" from the weekday service | Let `--type solo` pick per date, or use `--dow sat,sun` |
| Booking on a vague request | Dry run first; `--confirm` only for a named date, time, length, studio |
| Sitting on the payment link | Send it in the first reply after `--confirm`; it expires |
| Booking without adding the calendar event, or adding it from the site's link | Create it as part of `--confirm`, every time, from the `CALENDAR:` line (the link is 4h early) |
| Guessing the room by tier | `studios` shows kit and cymbals per free room; the user has preferences (see project memory) |
