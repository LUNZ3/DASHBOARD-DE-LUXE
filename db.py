"""STRYKE data layer: SQLite persistence + all business rules (server-side)."""
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _env(name, default):
    return os.environ.get(name, default)


DB_PATH = _env("STRYKE_DB", "stryke.db")
PRIVATE_DIR = _env("STRYKE_PRIVATE_DIR", "private_uploads")
COMMISSION_PCT = float(_env("STRYKE_COMMISSION_PCT", "15"))
FREE_CANCEL_HOURS = int(_env("STRYKE_FREE_CANCEL_HOURS", "24"))
MIN_YEARS = int(_env("STRYKE_MIN_YEARS", "5"))
MIN_NOTICE_HOURS = int(_env("STRYKE_MIN_NOTICE_HOURS", "2"))
ADMIN_EMAIL = _env("STRYKE_ADMIN_EMAIL", "").strip().lower()

SPORTS = ["Boxing", "MMA", "Muay Thai", "Kickboxing / K-1", "Brazilian Jiu-Jitsu", "Wrestling"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ACTIVE = ("pending", "confirmed")

# name -> (lat, lon, country, tz, currency)  real city-centre coordinates
CITIES = {
    "Oslo": (59.9139, 10.7522, "NO", "Europe/Oslo", "NOK"),
    "Bergen": (60.3913, 5.3221, "NO", "Europe/Oslo", "NOK"),
    "Trondheim": (63.4305, 10.3951, "NO", "Europe/Oslo", "NOK"),
    "Stavanger": (58.9700, 5.7331, "NO", "Europe/Oslo", "NOK"),
    "Stockholm": (59.3293, 18.0686, "SE", "Europe/Stockholm", "SEK"),
    "Copenhagen": (55.6761, 12.5683, "DK", "Europe/Copenhagen", "DKK"),
    "London": (51.5074, -0.1278, "GB", "Europe/London", "GBP"),
    "Berlin": (52.5200, 13.4050, "DE", "Europe/Berlin", "EUR"),
    "Amsterdam": (52.3676, 4.9041, "NL", "Europe/Amsterdam", "EUR"),
    "Madrid": (40.4168, -3.7038, "ES", "Europe/Madrid", "EUR"),
    "New York": (40.7128, -74.0060, "US", "America/New_York", "USD"),
    "Bangkok": (13.7563, 100.5018, "TH", "Asia/Bangkok", "THB"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL, suspended INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS coaches(
  id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), name TEXT NOT NULL,
  city TEXT NOT NULL, country TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
  tz TEXT NOT NULL, currency TEXT NOT NULL, price_cents INTEGER NOT NULL,
  session_minutes INTEGER NOT NULL DEFAULT 60, sports TEXT NOT NULL, languages TEXT NOT NULL,
  years_exp INTEGER NOT NULL DEFAULT 0, style TEXT DEFAULT '', bio TEXT DEFAULT '',
  record TEXT DEFAULT '', achievements TEXT DEFAULT '', qualifications TEXT DEFAULT '',
  verified INTEGER NOT NULL DEFAULT 0, verified_at TEXT, demo INTEGER NOT NULL DEFAULT 0,
  suspended INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS availability(
  id INTEGER PRIMARY KEY, coach_id INTEGER NOT NULL REFERENCES coaches(id),
  weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6), start_t TEXT NOT NULL, end_t TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY, coach_id INTEGER NOT NULL REFERENCES coaches(id),
  user_id INTEGER NOT NULL REFERENCES users(id), start_utc TEXT NOT NULL, end_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','confirmed','completed','cancelled','disputed','refunded')),
  price_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL, currency TEXT NOT NULL,
  payment_status TEXT NOT NULL DEFAULT 'unpaid', note TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_slot ON bookings(coach_id, start_utc)
  WHERE status IN ('pending','confirmed');
CREATE TABLE IF NOT EXISTS favourites(
  user_id INTEGER NOT NULL REFERENCES users(id), coach_id INTEGER NOT NULL REFERENCES coaches(id),
  PRIMARY KEY(user_id, coach_id));
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY, booking_id INTEGER UNIQUE NOT NULL REFERENCES bookings(id),
  coach_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), text TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), data TEXT NOT NULL,
  files TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL CHECK(status IN ('draft','submitted','under_review','needs_info','approved','rejected')),
  admin_note TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL, target TEXT, detail TEXT,
  created_at TEXT NOT NULL);
"""


class StrykeError(Exception):
    """User-presentable error."""


class SlotTaken(StrykeError):
    pass


def now_iso(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
    finally:
        c.close()


@contextmanager
def tx():
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM coaches").fetchone()[0] == 0:
            _seed(c)


# ---------------------------------------------------------------- geo / money
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def money(cents, cur):
    return f"{cents / 100:,.0f} {cur}".replace(",", " ")


# ---------------------------------------------------------------------- seed
def _seed(c):
    """DEMO coaches. Fictional people, NOT verified, flagged demo=1."""
    demo = [
        ("Demo: Marcus Hale", "Oslo", ["Boxing", "Kickboxing / K-1"], ["English", "Norwegian"], 450, 12,
         "Pressure boxer, fundamentals first", "Fictional demo profile. Teaches footwork, jab discipline and ring IQ.",
         "Demo: 14-3 (illustrative)", "Demo: regional title (illustrative)", "Demo: coaching course (illustrative)"),
        ("Demo: Sofia Lindqvist", "Stockholm", ["Brazilian Jiu-Jitsu", "Wrestling"], ["English", "Swedish"], 520, 9,
         "Technical, patient, competition-minded", "Fictional demo profile. Guard retention and takedown entries.",
         "Demo: n/a", "Demo: purple belt (illustrative)", "Demo: instructor certificate (illustrative)"),
        ("Demo: Arthit Chaiyasit", "Bangkok", ["Muay Thai"], ["English", "Thai"], 350, 15,
         "Traditional clinch and elbows", "Fictional demo profile. Pad work and clinch drills.",
         "Demo: 40-12 (illustrative)", "Demo: stadium bouts (illustrative)", "Demo: camp trainer (illustrative)"),
        ("Demo: Jonas Berg", "Bergen", ["MMA", "Wrestling"], ["English", "Norwegian"], 480, 7,
         "Complete MMA, safe progressions", "Fictional demo profile. Cage wrestling and striking blends.",
         "Demo: 8-2 amateur (illustrative)", "Demo: national amateur finalist (illustrative)", "Demo: first-aid (illustrative)"),
        ("Demo: Emma Clarke", "London", ["Boxing", "MMA"], ["English"], 60, 6,
         "Fitness-forward fight training", "Fictional demo profile. Conditioning plus technical rounds.",
         "Demo: n/a", "Demo: amateur boxing medalist (illustrative)", "Demo: PT level 3 (illustrative)"),
        ("Demo: Mateo Ruiz", "Madrid", ["Brazilian Jiu-Jitsu", "Kickboxing / K-1"], ["English", "Spanish"], 55, 11,
         "Systematic, drill-heavy", "Fictional demo profile. Passing systems and kick defence.",
         "Demo: n/a", "Demo: brown belt (illustrative)", "Demo: coach licence (illustrative)"),
    ]
    for name, city, sports, langs, price, yrs, style, bio, rec, ach, qual in demo:
        lat, lon, country, tz, cur = CITIES[city]
        c.execute(
            "INSERT INTO coaches(name,city,country,lat,lon,tz,currency,price_cents,session_minutes,sports,languages,"
            "years_exp,style,bio,record,achievements,qualifications,verified,demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,1)",
            (name, city, country, lat, lon, tz, cur, price * 100, 60, json.dumps(sports), json.dumps(langs),
             yrs, style, bio, rec, ach, qual))
        cid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        for wd in (0, 1, 2, 3, 4):
            c.execute("INSERT INTO availability(coach_id,weekday,start_t,end_t) VALUES(?,?,?,?)", (cid, wd, "17:00", "20:00"))
        c.execute("INSERT INTO availability(coach_id,weekday,start_t,end_t) VALUES(?,?,?,?)", (cid, 5, "10:00", "14:00"))


# ---------------------------------------------------------------------- auth
def _hash(pw, salt_hex):
    return hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1).hex()


def register(email, name, password):
    email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise StrykeError("Enter a valid email address.")
    if len(name.strip()) < 2:
        raise StrykeError("Enter your name.")
    if len(password) < 8:
        raise StrykeError("Password must be at least 8 characters.")
    salt = secrets.token_hex(16)
    try:
        with conn() as c:
            c.execute("INSERT INTO users(email,name,pw_hash,salt,created_at) VALUES(?,?,?,?,?)",
                      (email, name.strip(), _hash(password, salt), salt, now_iso()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        raise StrykeError("An account with this email already exists.")


def login(email, password):
    with conn() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not u or not secrets.compare_digest(u["pw_hash"], _hash(password, u["salt"])):
        raise StrykeError("Wrong email or password.")
    if u["suspended"]:
        raise StrykeError("This account is suspended.")
    return u["id"]


def get_user(uid):
    if not uid:
        return None
    with conn() as c:
        u = c.execute("SELECT id,email,name,suspended FROM users WHERE id=?", (uid,)).fetchone()
    return dict(u) if u and not u["suspended"] else None


def is_admin(user):
    """Server-side admin check: the account's email must equal STRYKE_ADMIN_EMAIL."""
    return bool(user and ADMIN_EMAIL and user["email"].lower() == ADMIN_EMAIL)


def _require_admin(user):
    if not is_admin(user):
        raise PermissionError("Admin access required.")


def audit(c, actor, action, target="", detail=""):
    c.execute("INSERT INTO audit_log(actor_id,action,target,detail,created_at) VALUES(?,?,?,?,?)",
              (actor["id"] if actor else None, action, str(target), detail, now_iso()))


# ------------------------------------------------------------------- coaches
def _coach_dict(r):
    d = dict(r)
    d["sports"] = json.loads(d["sports"])
    d["languages"] = json.loads(d["languages"])
    return d


def get_coach(cid):
    with conn() as c:
        r = c.execute(
            "SELECT co.*, (SELECT AVG(rating) FROM reviews WHERE coach_id=co.id) AS rating,"
            " (SELECT COUNT(*) FROM reviews WHERE coach_id=co.id) AS n_reviews FROM coaches co WHERE id=?",
            (cid,)).fetchone()
    return _coach_dict(r) if r else None


def coach_for_user(uid):
    with conn() as c:
        r = c.execute("SELECT id FROM coaches WHERE user_id=?", (uid,)).fetchone()
    return get_coach(r["id"]) if r else None


def search_coaches(q="", sports=None, city="", max_price=None, min_years=0, language="",
                   min_rating=0, only_available=False, origin=None, sort="Best match"):
    with conn() as c:
        rows = c.execute(
            "SELECT co.*, (SELECT AVG(rating) FROM reviews WHERE coach_id=co.id) AS rating,"
            " (SELECT COUNT(*) FROM reviews WHERE coach_id=co.id) AS n_reviews FROM coaches co WHERE suspended=0"
        ).fetchall()
        out = []
        for r in rows:
            d = _coach_dict(r)
            hay = " ".join([d["name"], d["city"], d["bio"], d["style"], " ".join(d["sports"])]).lower()
            if q and q.lower() not in hay:
                continue
            if sports and not set(sports) & set(d["sports"]):
                continue
            if city and d["city"] != city:
                continue
            if max_price is not None and d["price_cents"] / 100 > max_price:
                continue
            if d["years_exp"] < min_years:
                continue
            if language and language not in d["languages"]:
                continue
            if min_rating and (d["rating"] is None or d["rating"] < min_rating):
                continue
            d["next_slot"] = None
            slots = _slots(c, d)
            if slots:
                d["next_slot"] = slots[0]
            if only_available and not slots:
                continue
            d["distance_km"] = haversine_km(origin["lat"], origin["lon"], d["lat"], d["lon"]) if origin else None
            out.append(d)
    keys = {
        "Distance": lambda d: (d["distance_km"] is None, d["distance_km"] or 0),
        "Price (low to high)": lambda d: d["price_cents"] / 100,
        "Rating": lambda d: -(d["rating"] or 0),
        "Experience": lambda d: -d["years_exp"],
    }
    if sort in keys:
        out.sort(key=keys[sort])
    return out


def update_coach(uid, fields):
    """Coaches may edit profile fields only. Verification can never be changed here."""
    allowed = {"bio", "style", "price_cents", "session_minutes", "languages", "sports", "record",
               "achievements", "qualifications"}
    coach = coach_for_user(uid)
    if not coach:
        raise PermissionError("No coach profile for this account.")
    clean = {k: v for k, v in fields.items() if k in allowed}
    if "price_cents" in clean and clean["price_cents"] < 0:
        raise StrykeError("Price cannot be negative.")
    if "session_minutes" in clean and clean["session_minutes"] not in (30, 45, 60, 90, 120):
        raise StrykeError("Choose a standard session length.")
    for k in ("languages", "sports"):
        if k in clean:
            clean[k] = json.dumps(clean[k])
    if not clean:
        return
    with conn() as c:
        c.execute(f"UPDATE coaches SET {', '.join(k + '=?' for k in clean)} WHERE id=?", (*clean.values(), coach["id"]))


# -------------------------------------------------------------- availability
def _t(s):
    h, m = s.split(":")
    return int(h), int(m)


def _slots(c, coach, days=14):
    tz = ZoneInfo(coach["tz"])
    now = datetime.now(timezone.utc)
    dur = timedelta(minutes=coach["session_minutes"])
    wins = c.execute("SELECT weekday,start_t,end_t FROM availability WHERE coach_id=?", (coach["id"],)).fetchall()
    busy = [(_p(r["start_utc"]), _p(r["end_utc"])) for r in c.execute(
        "SELECT start_utc,end_utc FROM bookings WHERE coach_id=? AND status IN ('pending','confirmed') AND end_utc>?",
        (coach["id"], now_iso(now)))]
    today = now.astimezone(tz).date()
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        for w in wins:
            if w["weekday"] != d.weekday():
                continue
            sh, sm = _t(w["start_t"])
            eh, em = _t(w["end_t"])
            s = datetime(d.year, d.month, d.day, sh, sm, tzinfo=tz).astimezone(timezone.utc)
            e = datetime(d.year, d.month, d.day, eh, em, tzinfo=tz).astimezone(timezone.utc)
            while s + dur <= e:
                if s > now + timedelta(hours=MIN_NOTICE_HOURS) and not any(s < be and s + dur > bs for bs, be in busy):
                    out.append(s)
                s += dur
    return sorted(set(out))


def free_slots(coach_id, days=14):
    coach = get_coach(coach_id)
    if not coach or coach["suspended"]:
        return []
    with conn() as c:
        return _slots(c, coach, days)


def get_availability(coach_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT weekday,start_t,end_t FROM availability WHERE coach_id=? ORDER BY weekday,start_t", (coach_id,))]


def set_availability(uid, rows):
    coach = coach_for_user(uid)
    if not coach:
        raise PermissionError("No coach profile for this account.")
    clean = []
    for r in rows:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(r["start_t"])) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(r["end_t"])):
            raise StrykeError("Times must be HH:MM (24h).")
        if r["start_t"] >= r["end_t"]:
            raise StrykeError("Start must be before end.")
        clean.append((coach["id"], int(r["weekday"]), r["start_t"], r["end_t"]))
    with tx() as c:
        c.execute("DELETE FROM availability WHERE coach_id=?", (coach["id"],))
        c.executemany("INSERT INTO availability(coach_id,weekday,start_t,end_t) VALUES(?,?,?,?)", clean)


# ------------------------------------------------------------------ bookings
def price_breakdown(coach):
    price = coach["price_cents"]
    fee = round(price * COMMISSION_PCT / 100)
    return {"price": price, "fee": fee, "coach_gets": price - fee, "currency": coach["currency"], "pct": COMMISSION_PCT}


def create_booking(user_id, coach_id, start_utc, note=""):
    """Atomic: re-validates the slot inside a write transaction. Raises SlotTaken if gone.
    Test mode: no payment provider is wired, so no money moves; payment_status says so."""
    start_iso = now_iso(start_utc)
    try:
        with tx() as c:
            r = c.execute("SELECT * FROM coaches WHERE id=?", (coach_id,)).fetchone()
            if not r or r["suspended"]:
                raise StrykeError("This coach is not available.")
            if c.execute("SELECT suspended FROM users WHERE id=?", (user_id,)).fetchone()["suspended"]:
                raise StrykeError("Your account is suspended.")
            coach = _coach_dict(r)
            if start_utc not in _slots(c, coach):
                raise SlotTaken("That time is no longer available. Please pick another slot.")
            end = start_utc + timedelta(minutes=coach["session_minutes"])
            if c.execute("SELECT 1 FROM bookings WHERE coach_id=? AND status IN ('pending','confirmed')"
                         " AND start_utc<? AND end_utc>?", (coach_id, now_iso(end), start_iso)).fetchone():
                raise SlotTaken("That time overlaps another booking.")
            pb = price_breakdown(coach)
            c.execute(
                "INSERT INTO bookings(coach_id,user_id,start_utc,end_utc,status,price_cents,fee_cents,currency,"
                "payment_status,note,created_at) VALUES(?,?,?,?,'confirmed',?,?,?,'test_mode_no_charge',?,?)",
                (coach_id, user_id, start_iso, now_iso(end), pb["price"], pb["fee"], pb["currency"], note[:500], now_iso()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        raise SlotTaken("Someone just booked that slot. Please pick another.")


def user_bookings(uid):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT b.*, co.name AS coach_name, co.tz, co.city, "
            "(SELECT 1 FROM reviews WHERE booking_id=b.id) AS reviewed "
            "FROM bookings b JOIN coaches co ON co.id=b.coach_id WHERE b.user_id=? ORDER BY start_utc DESC", (uid,))]


def coach_bookings(coach_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT b.*, u.name AS customer_name FROM bookings b JOIN users u ON u.id=b.user_id "
            "WHERE b.coach_id=? ORDER BY start_utc DESC", (coach_id,))]


def cancel_booking(user_id, booking_id):
    """Customer cancellation. Free if >= FREE_CANCEL_HOURS before start; later = no refund (policy)."""
    with tx() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id)).fetchone()
        if not b:
            raise PermissionError("Booking not found.")
        if b["status"] not in ACTIVE:
            raise StrykeError("This booking can no longer be cancelled.")
        hours = (_p(b["start_utc"]) - datetime.now(timezone.utc)).total_seconds() / 3600
        if hours < 0:
            raise StrykeError("This session has already started.")
        refundable = hours >= FREE_CANCEL_HOURS
        c.execute("UPDATE bookings SET status='cancelled', note=note||? WHERE id=?",
                  (f" [cancelled; {'free cancellation' if refundable else 'late cancellation, no refund per policy'}]", booking_id))
        return refundable


def complete_booking(actor_uid, booking_id):
    """Only the booked coach (or admin) may complete, and only once the session has started."""
    with tx() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if not b:
            raise StrykeError("Booking not found.")
        coach = c.execute("SELECT user_id FROM coaches WHERE id=?", (b["coach_id"],)).fetchone()
        actor = get_user(actor_uid)
        if not (coach["user_id"] == actor_uid or is_admin(actor)):
            raise PermissionError("Not allowed.")
        if b["status"] != "confirmed":
            raise StrykeError("Only confirmed bookings can be completed.")
        if _p(b["start_utc"]) > datetime.now(timezone.utc):
            raise StrykeError("The session has not happened yet.")
        c.execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))


def add_review(user_id, booking_id, rating, text):
    with tx() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id)).fetchone()
        if not b or b["status"] != "completed":
            raise StrykeError("You can only review a completed session.")
        if not 1 <= int(rating) <= 5:
            raise StrykeError("Rating must be 1-5.")
        try:
            c.execute("INSERT INTO reviews(booking_id,coach_id,user_id,rating,text,created_at) VALUES(?,?,?,?,?,?)",
                      (booking_id, b["coach_id"], user_id, int(rating), text[:1000], now_iso()))
        except sqlite3.IntegrityError:
            raise StrykeError("You already reviewed this session.")


def reviews_for(coach_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT r.rating,r.text,r.created_at,u.name FROM reviews r JOIN users u ON u.id=r.user_id "
            "WHERE r.coach_id=? ORDER BY r.created_at DESC", (coach_id,))]


# ---------------------------------------------------------------- favourites
def toggle_favourite(uid, coach_id):
    with conn() as c:
        if c.execute("SELECT 1 FROM favourites WHERE user_id=? AND coach_id=?", (uid, coach_id)).fetchone():
            c.execute("DELETE FROM favourites WHERE user_id=? AND coach_id=?", (uid, coach_id))
            return False
        c.execute("INSERT INTO favourites VALUES(?,?)", (uid, coach_id))
        return True


def favourite_ids(uid):
    with conn() as c:
        return {r[0] for r in c.execute("SELECT coach_id FROM favourites WHERE user_id=?", (uid,))}


# -------------------------------------------------------------- applications
def eligible(fight_years, has_achievements, coaching_years):
    return (fight_years >= MIN_YEARS and has_achievements) or coaching_years >= MIN_YEARS


def _safe_name(n):
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(n))[:80]


def get_application(uid):
    with conn() as c:
        r = c.execute("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["data"] = json.loads(d["data"])
    d["files"] = json.loads(d["files"])
    return d


def submit_application(uid, data, files):
    """files: list of (filename, bytes). Stored on private disk, never served publicly."""
    if data["city"] not in CITIES:
        raise StrykeError("Choose a supported city.")
    if not data["sports"]:
        raise StrykeError("Select at least one sport.")
    if not eligible(data["fight_years"], bool(data["achievements"].strip()), data["coaching_years"]):
        raise StrykeError(f"Eligibility policy not met: at least {MIN_YEARS} years of documented competitive experience "
                          f"(with fights/achievements) OR {MIN_YEARS} years of coaching experience.")
    prev = get_application(uid)
    if prev and prev["status"] in ("submitted", "under_review", "approved"):
        raise StrykeError("You already have an application in progress or approved.")
    saved = list(prev["files"]) if prev else []
    for name, blob in files:
        if len(blob) > 10 * 1024 * 1024:
            raise StrykeError(f"{name} is larger than 10 MB.")
        if not name.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            raise StrykeError("Evidence must be PDF, JPG or PNG.")
    if not saved and not files:
        raise StrykeError("Upload at least one piece of evidence (certificate, fight record, etc.).")
    with tx() as c:
        if prev and prev["status"] in ("needs_info", "draft", "rejected"):
            aid = prev["id"]
            c.execute("UPDATE applications SET data=?,status='submitted',updated_at=? WHERE id=?",
                      (json.dumps(data), now_iso(), aid))
        else:
            c.execute("INSERT INTO applications(user_id,data,status,created_at,updated_at) VALUES(?,?, 'submitted',?,?)",
                      (uid, json.dumps(data), now_iso(), now_iso()))
            aid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        folder = os.path.join(PRIVATE_DIR, f"app_{aid}")
        os.makedirs(folder, exist_ok=True)
        for name, blob in files:
            fn = f"{secrets.token_hex(4)}_{_safe_name(name)}"
            with open(os.path.join(folder, fn), "wb") as f:
                f.write(blob)
            saved.append(fn)
        c.execute("UPDATE applications SET files=? WHERE id=?", (json.dumps(saved), aid))
        audit(c, {"id": uid}, "application_submitted", aid)
    return aid


def list_applications(admin):
    _require_admin(admin)
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT a.*, u.email, u.name AS uname FROM applications a JOIN users u ON u.id=a.user_id ORDER BY a.id DESC")]
    for r in rows:
        r["data"] = json.loads(r["data"])
        r["files"] = json.loads(r["files"])
    return rows


def read_evidence(admin, app_id, filename):
    _require_admin(admin)
    path = os.path.join(PRIVATE_DIR, f"app_{int(app_id)}", os.path.basename(filename))
    with open(path, "rb") as f:
        return f.read()


def review_application(admin, app_id, new_status, note=""):
    """Only an admin can change verification. Approval creates the VERIFIED public profile."""
    _require_admin(admin)
    if new_status not in ("under_review", "needs_info", "approved", "rejected"):
        raise StrykeError("Invalid status.")
    if new_status in ("needs_info", "rejected") and not note.strip():
        raise StrykeError("Add a note explaining the decision to the applicant.")
    with tx() as c:
        a = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        if not a:
            raise StrykeError("Application not found.")
        if a["status"] in ("draft",):
            raise StrykeError("Application has not been submitted.")
        d = json.loads(a["data"])
        if new_status == "approved":
            if c.execute("SELECT 1 FROM coaches WHERE user_id=?", (a["user_id"],)).fetchone():
                raise StrykeError("This user already has a coach profile.")
            lat, lon, country, tz, cur = CITIES[d["city"]]
            c.execute(
                "INSERT INTO coaches(user_id,name,city,country,lat,lon,tz,currency,price_cents,session_minutes,sports,languages,"
                "years_exp,style,bio,record,achievements,qualifications,verified,verified_at,demo) "
                "VALUES(?,?,?,?,?,?,?,?,?,60,?,?,?,?,?,?,?,?,1,?,0)",
                (a["user_id"], d["full_name"], d["city"], country, lat, lon, tz, cur, int(d["price"]) * 100,
                 json.dumps(d["sports"]), json.dumps(d["languages"]), max(d["fight_years"], d["coaching_years"]),
                 d.get("style", ""), d["bio"], d["record"], d["achievements"], d["qualifications"], now_iso()))
        c.execute("UPDATE applications SET status=?, admin_note=?, updated_at=? WHERE id=?",
                  (new_status, note, now_iso(), app_id))
        audit(c, admin, f"application_{new_status}", app_id, note)


def set_suspended(admin, kind, target_id, value):
    _require_admin(admin)
    table = {"coach": "coaches", "user": "users"}[kind]
    if kind == "user" and target_id == admin["id"]:
        raise StrykeError("You cannot suspend yourself.")
    with tx() as c:
        c.execute(f"UPDATE {table} SET suspended=? WHERE id=?", (1 if value else 0, target_id))
        audit(c, admin, f"{kind}_{'suspended' if value else 'unsuspended'}", target_id)


def metrics(admin):
    _require_admin(admin)
    with conn() as c:
        q = lambda s: c.execute(s).fetchone()[0] or 0
        return {
            "Completed bookings": q("SELECT COUNT(*) FROM bookings WHERE status='completed'"),
            "Confirmed (upcoming)": q("SELECT COUNT(*) FROM bookings WHERE status='confirmed'"),
            "Cancellations": q("SELECT COUNT(*) FROM bookings WHERE status='cancelled'"),
            "Verified coaches": q("SELECT COUNT(*) FROM coaches WHERE verified=1 AND suspended=0"),
            "Customers": q("SELECT COUNT(*) FROM users"),
            "Repeat customers": q("SELECT COUNT(*) FROM (SELECT user_id FROM bookings WHERE status='completed' GROUP BY user_id HAVING COUNT(*)>1)"),
            "Booking value, completed (minor units, mixed currencies)": q("SELECT SUM(price_cents) FROM bookings WHERE status='completed'"),
            "Platform fees, completed (minor units, mixed currencies)": q("SELECT SUM(fee_cents) FROM bookings WHERE status='completed'"),
        }


def admin_tables(admin):
    _require_admin(admin)
    with conn() as c:
        return {
            "coaches": [dict(r) for r in c.execute("SELECT id,name,city,verified,demo,suspended FROM coaches")],
            "users": [dict(r) for r in c.execute("SELECT id,email,name,suspended,created_at FROM users")],
            "bookings": [dict(r) for r in c.execute("SELECT id,coach_id,user_id,start_utc,status,price_cents,fee_cents,currency,payment_status FROM bookings ORDER BY id DESC LIMIT 200")],
            "audit": [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")],
        }
