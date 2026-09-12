# geary-ave-skill

A Claude Code skill for booking rehearsal time at [Geary Ave Rehearsal Studios](https://gearyaverehearsal.com)
in Toronto. No browser: the site's booking wizard (Booknetic) answers plain HTTP, so availability comes back
in about a second and a booking goes straight to the Stripe payment link.

## Install

```
/plugin marketplace add trianglegrrl/clave-skills
/plugin install geary-ave@clave
```

or copy `skills/geary-ave` into `~/.claude/skills/`. Needs only `python3`.

Availability and studio lookups work with no setup. To book, the site has to already know you
(book once by hand), and the phone number it knows you by goes in a secrets file:

```
mkdir -p ~/.config && printf 'PHONE=4165551234\n' > ~/.config/secrets.env && chmod 600 ~/.config/secrets.env
```

## Commands

| Command | Does |
|---|---|
| `geary.py avail --hours 3 [--days 14] [--dow sat,sun] [--before 17:00] [--studio 11]` | start times per day |
| `geary.py studios --date D --time HH:MM --hours 3` | which rooms are free for that slot, with drum kit and cymbals |
| `geary.py book --date D --time HH:MM --hours 3 --studio 11` | prices the slot (dry run) |
| `geary.py book ... --confirm` | books it and prints the Stripe link to pay |
| `geary.py cancel-unpaid --payment-id ID` | removes a booking you decided not to pay for |
| `geary.py rooms [--match "maple custom"]` | gear reference for every studio |

`--type` defaults to `solo`, which picks Weekday Solo or Weekend Solo from the date. Band rooms are
`basic`, `standard`, `standard-plus`, `premium` (two-hour minimum).

The studio gear list is a snapshot of [xbio.ca/geary](https://xbio.ca/geary/), an unofficial scrape of the
studio pages. The phone number is read from the secrets file inside the script and never passed on a
command line.

MIT.
