"""Thin client for the Booknetic booking API behind gearyaverehearsal.com/booking/.

Every step of the booking wizard is one POST to admin-ajax.php with the cart
serialised as JSON. Nothing needs a login, cookie, or signature, so the whole
flow up to the Stripe payment link works from plain HTTP.

Python 3.8+ (no f-string backslashes: this also runs on Ubuntu 22.04).
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

AJAX_URL = "https://gearyaverehearsal.com/wp-admin/admin-ajax.php"
BOOKING_URL = "https://gearyaverehearsal.com/booking/"
SECRETS_FILE = os.path.expanduser(os.environ.get("GEARY_SECRETS", "~/.config/secrets.env"))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

# service id, "extra hours" extra id, hours included in the base price, max extra hours
SERVICES = {
    "weekday": {"id": 4, "extra": 6, "base_hours": 1, "max_extra": 6, "label": "Weekday Solo"},
    "weekend": {"id": 5, "extra": 5, "base_hours": 1, "max_extra": 11, "label": "Weekend Solo"},
    "basic": {"id": 3, "extra": 4, "base_hours": 2, "max_extra": 10, "label": "Basic"},
    "standard": {"id": 2, "extra": 3, "base_hours": 2, "max_extra": 10, "label": "Standard"},
    "standard-plus": {"id": 9, "extra": 10, "base_hours": 2, "max_extra": 10, "label": "Standard Plus"},
    "premium": {"id": 1, "extra": 2, "base_hours": 2, "max_extra": 10, "label": "Premium"},
}
SOLO_TYPES = ("weekday", "weekend")


class GearyError(Exception):
    """Any failure the caller should report verbatim."""


def resolve_type(type_name, date):
    """'solo' picks weekday/weekend from the date; explicit names pass through."""
    if type_name in SERVICES:
        return type_name
    if type_name == "solo":
        if date is None:
            raise GearyError("type 'solo' needs a date to decide weekday vs weekend")
        return "weekend" if date.weekday() >= 5 else "weekday"
    raise GearyError("unknown booking type %r (use solo, weekday, weekend, basic, standard, standard-plus, premium)" % type_name)


def extras_for(type_name, hours):
    svc = SERVICES[type_name]
    extra_qty = hours - svc["base_hours"]
    if extra_qty < 0:
        raise GearyError("%s bookings are at least %dh" % (svc["label"], svc["base_hours"]))
    if extra_qty > svc["max_extra"]:
        raise GearyError("%s bookings max out at %dh" % (svc["label"], svc["base_hours"] + svc["max_extra"]))
    return [{"extra": svc["extra"], "quantity": extra_qty}] if extra_qty else []


def build_cart(type_name, hours, date="", time="", staff="", phone="", customer_id=0):
    svc = SERVICES[type_name]
    return [{
        "location": -1,
        "staff": staff,
        "service_category": "",
        "service": svc["id"],
        "service_extras": extras_for(type_name, hours),
        "date": date,
        "time": time,
        "brought_people_count": 0,
        "recurring_start_date": "",
        "recurring_end_date": "",
        "recurring_times": "{}",
        "appointments": "[]",
        "customer_id": customer_id,
        "customer_data": {"email": "", "first_name": "", "last_name": "", "phone": phone},
    }]


def post(action, cart, **fields):
    body = {
        "action": action,
        "cart": json.dumps(cart),
        "current": "0",
        "query_params": "{}",
        "client_time_zone": "-",
        "deposit_full_amount": "0",
        "payment_method": fields.pop("payment_method", "undefined"),
    }
    body.update(fields)
    req = urllib.request.Request(AJAX_URL, data=urllib.parse.urlencode(body).encode(), headers=HEADERS)
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.URLError as exc:
        raise GearyError("booking site unreachable: %s" % exc)
    try:
        data = json.loads(raw)
    except ValueError:
        raise GearyError("booking site returned non-JSON (%d bytes)" % len(raw))
    if data.get("status") == "error":
        msgs = [e.get("message", "") for e in data.get("errors", [])] or [data.get("error_msg", "error")]
        raise GearyError("; ".join(m for m in msgs if m))
    return data


def step(name, previous, cart, **fields):
    return post("bkntc_get_data", cart, current_step=name, previous_step=previous, **fields)


def month_slots(type_name, hours, year, month, staff=""):
    """{date: [(start, end), ...]} for one calendar month, all-studio unless staff is set."""
    cart = build_cart(type_name, hours, staff=staff)
    data = step("date_time", "service_extras", cart, year=str(year), month=str(month))
    dates = data.get("data", {}).get("dates", {})
    return {d: [(s["start_time"], s["end_time"]) for s in slots] for d, slots in dates.items()}


def free_studios(type_name, hours, date, time):
    """[(studio_number, name)] free for the slot."""
    cart = build_cart(type_name, hours, date=date, time=time)
    body = html.unescape(step("staff", "date_time", cart).get("html", ""))
    body = re.sub(r"\s+", " ", body)
    found = re.findall(r'data-id="(\d+)".*?booknetic_card_title_first">([^<]+)', body)
    return [(int(i), n.strip()) for i, n in found]


def load_phone():
    if not os.path.exists(SECRETS_FILE):
        raise GearyError("secrets file %s not found (needs PHONE=...)" % SECRETS_FILE)
    phone = ""
    with open(SECRETS_FILE) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("PHONE="):
                phone = line.split("=", 1)[1].strip().strip("'\"")
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) != 11:
        raise GearyError("PHONE in %s is not a 10-digit North American number" % SECRETS_FILE)
    return "+" + digits


def find_customer(type_name, hours, date, time, staff, phone):
    cart = build_cart(type_name, hours, date, time, staff, phone=phone)
    result = post("bkntc_check_customer_exist", cart)
    customer_id = result.get("customer_id")
    if not customer_id:
        raise GearyError("CUSTOMER_NOT_FOUND: the booking site does not recognise PHONE; book once by hand so it has your details")
    return int(customer_id)


def price_summary(type_name, hours, date, time, staff, phone, customer_id):
    """Runs cart + confirm_details (both read-only) and returns the totals text."""
    cart = build_cart(type_name, hours, date, time, staff, phone, customer_id)
    step("cart", "information", cart)
    data = step("confirm_details", "cart", cart, payment_method="stripe")
    text = re.sub(r"<[^>]+>", " ", html.unescape(data.get("html", "")))
    text = re.sub(r"\s+", " ", text)
    total = re.search(r"Total price\s*\$([\d.]+)", text)
    deposit = re.search(r"Deposit:\s*\$([\d.]+)", text)
    return {
        "total": float(total.group(1)) if total else None,
        "deposit": float(deposit.group(1)) if deposit else None,
        "lines": re.findall(r"([A-Za-z][A-Za-z \[\]x0-9]+?)\s+\$([\d.]+)", text.split("Total price")[0]),
    }


def page_info_token():
    """The signed 'info' blob the page embeds; harmless if missing."""
    try:
        page = urllib.request.urlopen(urllib.request.Request(BOOKING_URL, headers=HEADERS), timeout=60).read().decode("utf-8", "ignore")
    except urllib.error.URLError:
        return ""
    match = re.search(r'data-info="([^"]*)"', page)
    return match.group(1) if match else ""


def confirm_booking(type_name, hours, date, time, staff, phone, customer_id):
    """Creates the appointment. Returns the raw response (id, payment_id, url...)."""
    cart = build_cart(type_name, hours, date, time, staff, phone, customer_id)
    return step("confirm", "confirm_details", cart, payment_method="stripe", info=page_info_token())


def delete_unpaid(payment_id):
    return post("bkntc_delete_unpaid_appointment", [], payment_id=str(payment_id))


def studios_reference():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "studios.json")
    with open(path) as fh:
        return json.load(fh)["studios"]


def fail(message, code=1):
    sys.stderr.write("ERROR: %s\n" % message)
    sys.exit(code)
