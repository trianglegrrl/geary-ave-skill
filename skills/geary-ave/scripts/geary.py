#!/usr/bin/env python3
"""Geary Ave Rehearsal Studios: availability, free rooms, and booking from the CLI.

  geary.py avail   --hours 3 [--type solo] [--days 14 | --date D | --from D --to D | --month YYYY-MM]
                   [--dow sat,sun] [--after HH:MM] [--before HH:MM] [--studio N] [--json]
  geary.py studios --date D --time HH:MM --hours 3 [--type solo] [--json]
  geary.py book    --date D --time HH:MM --hours 3 --studio N [--type solo] [--confirm] [--json]
  geary.py cancel-unpaid --payment-id ID
  geary.py rooms   [--match text] [--json]

Times are Toronto local, 24h. A booking is only created with --confirm; it then
prints the Stripe link that has to be paid within the site's expiry window.
"""
import argparse
import datetime as dt
import json
import sys

import geary_api as api

DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        api.fail("bad date %r (want YYYY-MM-DD)" % text)


def parse_time(text):
    try:
        return dt.datetime.strptime(text, "%H:%M").time()
    except ValueError:
        api.fail("bad time %r (want HH:MM, 24h)" % text)


def date_range(args):
    today = dt.date.today()
    if args.date:
        d = parse_date(args.date)
        return d, d
    if args.month:
        first = parse_date(args.month + "-01")
        nxt = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        return max(first, today), nxt - dt.timedelta(days=1)
    if getattr(args, "from_date", None):
        start = parse_date(args.from_date)
        end = parse_date(args.to_date) if args.to_date else start + dt.timedelta(days=args.days)
        return start, end
    return today, today + dt.timedelta(days=args.days)


def months_between(start, end):
    cur = start.replace(day=1)
    while cur <= end:
        yield cur.year, cur.month
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def end_minutes(end_text):
    hh, mm = end_text.split(":")
    minutes = int(hh) * 60 + int(mm)
    return minutes if minutes else 24 * 60  # "00:00" end means midnight


def collect_slots(args, start, end):
    """[(date, type, start, end)] filtered to the range and the CLI filters."""
    types = list(api.SOLO_TYPES) if args.type == "solo" else [api.resolve_type(args.type, None)]
    wanted_dow = set(d.strip().lower()[:3] for d in args.dow.split(",")) if args.dow else None
    after = parse_time(args.after) if args.after else None
    before = parse_time(args.before) if args.before else None
    rows = []
    for year, month in months_between(start, end):
        for type_name in types:
            if type_name == "weekday" and not any(d.weekday() < 5 for d in days_in(start, end, year, month)):
                continue
            if type_name == "weekend" and not any(d.weekday() >= 5 for d in days_in(start, end, year, month)):
                continue
            for date_text, slots in api.month_slots(type_name, args.hours, year, month, staff=args.studio or "").items():
                d = dt.date.fromisoformat(date_text)
                if d < start or d > end or not slots:
                    continue
                if wanted_dow and DOW[d.weekday()] not in wanted_dow:
                    continue
                for s, e in slots:
                    if after and parse_time(s) < after:
                        continue
                    if before and end_minutes(e) > before.hour * 60 + before.minute:
                        continue
                    rows.append((date_text, type_name, s, e))
    rows.sort()
    return rows


def days_in(start, end, year, month):
    d = max(start, dt.date(year, month, 1))
    while d <= end and d.month == month:
        yield d
        d += dt.timedelta(days=1)


def cmd_avail(args):
    if args.type not in ("solo",) and args.type not in api.SERVICES:
        api.fail("unknown --type %r" % args.type)
    start, end = date_range(args)
    rows = collect_slots(args, start, end)
    if args.json:
        print(json.dumps([{"date": d, "type": t, "start": s, "end": e} for d, t, s, e in rows]))
        return
    if not rows:
        print("No %dh %s slots between %s and %s%s." % (
            args.hours, args.type, start, end, " in Studio %s" % args.studio if args.studio else ""))
        return
    by_date = {}
    for d, t, s, e in rows:
        by_date.setdefault((d, t), []).append("%s-%s" % (s, e))
    for (d, t), times in by_date.items():
        day = dt.date.fromisoformat(d)
        print("%s %s  %-8s %s" % (day.strftime("%a"), d, api.SERVICES[t]["label"].split()[0].lower(), "  ".join(times)))


def cmd_studios(args):
    date = parse_date(args.date)
    parse_time(args.time)
    type_name = api.resolve_type(args.type, date)
    api.extras_for(type_name, args.hours)
    free = api.free_studios(type_name, args.hours, args.date, args.time)
    ref = {s["id"]: s for s in api.studios_reference()}
    rows = []
    for number, name in free:
        info = ref.get(number, {})
        rows.append({"studio": number, "name": name, "tier": info.get("tier", ""),
                     "drum_kit": info.get("drum_kit", ""), "cymbals": info.get("cymbals", "")})
    if args.json:
        print(json.dumps(rows))
        return
    if not rows:
        print("No studio free for %dh %s on %s at %s." % (args.hours, type_name, args.date, args.time))
        sys.exit(2)
    for r in rows:
        print("%-10s %-22s %s / %s" % (r["name"], r["tier"], r["drum_kit"] or "?", r["cymbals"] or "?"))


def cmd_book(args):
    date = parse_date(args.date)
    parse_time(args.time)
    type_name = api.resolve_type(args.type, date)
    api.extras_for(type_name, args.hours)
    slots = api.month_slots(type_name, args.hours, date.year, date.month, staff=str(args.studio))
    if not any(s == args.time for s, _ in slots.get(args.date, [])):
        options = ["%s-%s" % (s, e) for s, e in slots.get(args.date, [])]
        api.fail("SLOT_UNAVAILABLE: Studio %d has no %dh slot at %s on %s. Free that day: %s" % (
            args.studio, args.hours, args.time, args.date, ", ".join(options) or "nothing"), 2)
    phone = api.load_phone()
    customer_id = api.find_customer(type_name, args.hours, args.date, args.time, str(args.studio), phone)
    summary = api.price_summary(type_name, args.hours, args.date, args.time, str(args.studio), phone, customer_id)
    result = {
        "type": type_name, "date": args.date, "start": args.time, "hours": args.hours, "studio": args.studio,
        "total": summary["total"], "deposit": summary["deposit"], "confirmed": False,
    }
    if args.confirm:
        response = api.confirm_booking(type_name, args.hours, args.date, args.time, str(args.studio), phone, customer_id)
        result.update({
            "confirmed": True,
            "appointment_id": response.get("id"),
            "payment_id": response.get("payment_id"),
            "payment_url": response.get("url"),
            "expires_in_seconds": response.get("payment_link_expiration_time") or response.get("expires_at"),
            "raw_keys": sorted(k for k in response.keys() if k not in ("html",)),
        })
    if args.json:
        print(json.dumps(result))
        return
    label = api.SERVICES[type_name]["label"]
    print("%s  %s %s  %dh  Studio %d  total $%s (deposit $%s now)" % (
        label, args.date, args.time, args.hours, args.studio, summary["total"], summary["deposit"]))
    if not args.confirm:
        print("DRY RUN: nothing booked. Re-run with --confirm to book.")
        return
    print("BOOKED appointment %s (payment %s)" % (result["appointment_id"], result["payment_id"]))
    if result["payment_url"]:
        print("PAY: %s" % result["payment_url"])
        if result["expires_in_seconds"]:
            print("Link expires in about %d minutes." % (int(result["expires_in_seconds"]) // 60))
    else:
        print("No payment link in the response; keys were: %s" % ", ".join(result["raw_keys"]))


def cmd_cancel_unpaid(args):
    response = api.delete_unpaid(args.payment_id)
    print(json.dumps(response) if args.json else "Unpaid booking %s removed (%s)." % (args.payment_id, response.get("status", "?")))


def cmd_rooms(args):
    needle = (args.match or "").lower()
    rows = []
    for s in api.studios_reference():
        blob = json.dumps(s).lower()
        if needle and needle not in blob:
            continue
        rows.append(s)
    if args.json:
        print(json.dumps(rows))
        return
    for s in rows:
        print("%-10s %-22s $%s/hr  %s / %s" % (s["name"], s["tier"], int(s["price_per_hr"]), s["drum_kit"] or "?", s["cymbals"] or "?"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, need_slot=False):
        p.add_argument("--hours", type=int, required=True, help="total booking length in hours")
        p.add_argument("--type", default="solo", help="solo (auto weekday/weekend), weekday, weekend, basic, standard, standard-plus, premium")
        p.add_argument("--json", action="store_true")
        if need_slot:
            p.add_argument("--date", required=True, help="YYYY-MM-DD")
            p.add_argument("--time", required=True, help="start HH:MM, 24h")

    p = sub.add_parser("avail", help="list available start times")
    common(p)
    p.add_argument("--date")
    p.add_argument("--month", help="YYYY-MM")
    p.add_argument("--from", dest="from_date")
    p.add_argument("--to", dest="to_date")
    p.add_argument("--days", type=int, default=14, help="days ahead when no date given (default 14)")
    p.add_argument("--dow", help="comma list of weekdays, e.g. sat,sun")
    p.add_argument("--after", help="only slots starting at or after HH:MM")
    p.add_argument("--before", help="only slots ending at or before HH:MM")
    p.add_argument("--studio", type=int, help="only this studio number")
    p.set_defaults(func=cmd_avail)

    p = sub.add_parser("studios", help="which studios are free for a slot")
    common(p, need_slot=True)
    p.set_defaults(func=cmd_studios)

    p = sub.add_parser("book", help="price a slot; --confirm books it and prints the Stripe link")
    common(p, need_slot=True)
    p.add_argument("--studio", type=int, required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_book)

    p = sub.add_parser("cancel-unpaid", help="remove a booking that has not been paid")
    p.add_argument("--payment-id", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cancel_unpaid)

    p = sub.add_parser("rooms", help="studio gear reference")
    p.add_argument("--match")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_rooms)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except api.GearyError as exc:
        api.fail(str(exc))


if __name__ == "__main__":
    main()
