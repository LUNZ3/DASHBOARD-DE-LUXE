"""STRYKE data layer: SQLite persistence + all business rules (server-side)."""
import base64
import hashlib
import io
import json
import math
import os
import re
import secrets
import sqlite3
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
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
GYM_SPORTS = SPORTS + ["Judo", "Karate", "Taekwondo", "Krav Maga", "Martial arts (general)"]
CURRENCIES = ["NOK", "SEK", "DKK", "EUR", "GBP", "USD", "THB"]

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
    "Phuket": (7.8804, 98.3923, "TH", "Asia/Bangkok", "THB"),
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
CREATE TABLE IF NOT EXISTS gyms(
  id INTEGER PRIMARY KEY, osm_id TEXT UNIQUE, name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
  address TEXT DEFAULT '', city TEXT DEFAULT '', country TEXT DEFAULT '', website TEXT DEFAULT '',
  phone TEXT DEFAULT '', email TEXT DEFAULT '', sports TEXT NOT NULL DEFAULT '[]', description TEXT DEFAULT '',
  logo_b64 TEXT DEFAULT '', logo_mime TEXT DEFAULT '',
  pt_status TEXT NOT NULL DEFAULT 'unknown' CHECK(pt_status IN ('unknown','yes','no')),
  pt_price_cents INTEGER, currency TEXT DEFAULT '',
  owner_id INTEGER REFERENCES users(id), claimant_id INTEGER REFERENCES users(id), claim_note TEXT DEFAULT '',
  claim_status TEXT NOT NULL DEFAULT 'none' CHECK(claim_status IN ('none','pending','approved')),
  verified INTEGER NOT NULL DEFAULT 0, suspended INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_gyms_geo ON gyms(lat, lon);
CREATE TABLE IF NOT EXISTS osm_cache(key TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0);
"""


class StrykeError(Exception):
    pass


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


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def money(cents, cur):
    if not cur:
        cur = "NOK"
    return f"{cents / 100:,.0f} {cur}".replace(",", " ")


def _seed(c):
    demo = [
        ("Demo: Marcus Hale", "Oslo", ["Boxing", "Kickboxing / K-1"], ["English", "Norwegian"], 450, 12,
         "Pressure boxer, fundamentals first", "Fictional demo profile.", "Demo: 14-3", "Demo: regional title", "Demo: course"),
        ("Demo: Arthit Chaiyasit", "Bangkok", ["Muay Thai"], ["English", "Thai"], 1200, 15,
         "Traditional clinch and elbows", "Fictional demo profile.", "Demo: 40-12", "Demo: stadium bouts", "Demo: camp trainer"),
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


def _hash(pw, salt_hex):
    return hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1).hex()


def register(email, name, password):
    email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise StrykeError("Enter a valid email address.")
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
    return bool(user and ADMIN_EMAIL and user["email"].lower() == ADMIN_EMAIL)


def audit(c, actor, action, target="", detail=""):
    c.execute("INSERT INTO audit_log(actor_id,action,target,detail,created_at) VALUES(?,?,?,?,?)",
              (actor["id"] if actor else None, action, str(target), detail, now_iso()))


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
            d["distance_km"] = haversine_km(origin["lat"], origin["lon"], d["lat"], d["lon"]) if origin else None
            out.append(d)
    return out


def _t(s):
    h, m = s.split(":")
    return int(h), int(m)


def _slots(c, coach, days=14):
    tz = ZoneInfo(coach["tz"])
    now = datetime.now(timezone.utc)
    dur = timedelta(minutes=coach["session_minutes"]) if "timedelta" in globals() else datetime.resolution
    # fallback duration
    dur = timedelta(minutes=60)
    wins = c.execute("SELECT weekday,start_t,end_t FROM availability WHERE coach_id=?", (coach["id"],)).fetchall()
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
                out.append(s)
                s += dur
    return sorted(set(out))


def free_slots(coach_id, days=14):
    coach = get_coach(coach_id)
    if not coach or coach["suspended"]:
        return []
    with conn() as c:
        return _slots(c, coach, days)


def price_breakdown(coach):
    price = coach["price_cents"]
    fee = round(price * COMMISSION_PCT / 100)
    return {"price": price, "fee": fee, "coach_gets": price - fee, "currency": coach["currency"], "pct": COMMISSION_PCT}


def create_booking(user_id, coach_id, start_utc, note=""):
    start_iso = now_iso(start_utc)
    with tx() as c:
        coach = get_coach(coach_id)
        end = start_utc + timedelta(minutes=coach["session_minutes"])
        pb = price_breakdown(coach)
        c.execute(
            "INSERT INTO bookings(coach_id,user_id,start_utc,end_utc,status,price_cents,fee_cents,currency,"
            "payment_status,note,created_at) VALUES(?,?,?,?,'confirmed',?,?,?,'test_mode_no_charge',?,?)",
            (coach_id, user_id, start_iso, now_iso(end), pb["price"], pb["fee"], pb["currency"], note[:500], now_iso()))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def user_bookings(uid):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT b.*, co.name AS coach_name, co.tz, co.city, "
            "(SELECT 1 FROM reviews WHERE booking_id=b.id) AS reviewed "
            "FROM bookings b JOIN coaches co ON co.id=b.coach_id WHERE b.user_id=? ORDER BY start_utc DESC", (uid,))]


def add_review(user_id, booking_id, rating, text):
    with tx() as c:
        b = c.execute("SELECT * FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id)).fetchone()
        c.execute("INSERT INTO reviews(booking_id,coach_id,user_id,rating,text,created_at) VALUES(?,?,?,?,?,?)",
                  (booking_id, b["coach_id"], user_id, int(rating), text[:1000], now_iso()))


def reviews_for(coach_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT r.rating,r.text,r.created_at,u.name FROM reviews r JOIN users u ON u.id=r.user_id "
            "WHERE r.coach_id=? ORDER BY r.created_at DESC", (coach_id,))]


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


# =========================================================================== GYMS & OSM
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = "STRYKE/1.0 (martial arts gym finder)"
_OSM_SPORT = {
    "boxing": "Boxing", "mma": "MMA", "muay_thai": "Muay Thai", "thai_boxing": "Muay Thai",
    "kickboxing": "Kickboxing / K-1", "brazilian_jiu_jitsu": "Brazilian Jiu-Jitsu", "bjj": "Brazilian Jiu-Jitsu",
    "wrestling": "Wrestling", "judo": "Judo", "karate": "Karate", "taekwondo": "Taekwondo", "krav_maga": "Krav Maga"
}


def _clean_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    return u[:200]


def geocode(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1, "addressdetails": 1})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10) as r:
            data = json.loads(r.read().decode())
    except Exception:
        raise StrykeError("Stedssøk er utilgjengelig akkurat nå.")
    if not data:
        return None
    d = data[0]
    a = d.get("address", {})
    return {"lat": float(d["lat"]), "lon": float(d["lon"]), "label": d.get("display_name", "")[:120],
            "city": a.get("city") or a.get("town") or a.get("village") or "",
            "country": (a.get("country_code") or "").upper()}


def _osm_sports(t):
    out = []
    for v in (t.get("sport") or "").split(";"):
        name = _OSM_SPORT.get(v.strip().lower())
        if name and name not in out:
            out.append(name)
    if not out:
        out = ["Martial arts (general)"]
    return out


def fetch_osm(lat, lon, radius_km=15, force=False):
    radius_km = max(1, min(float(radius_km), 50))
    key = f"{lat:.2f}:{lon:.2f}:{int(radius_km)}"
    with conn() as c:
        row = c.execute("SELECT fetched_at FROM osm_cache WHERE key=?", (key,)).fetchone()
    if row and not force and (datetime.now(timezone.utc) - _p(row["fetched_at"])).days < 7:
        return 0
    r = int(radius_km * 1000)
    sp = "boxing|martial_arts|mma|muay_thai|thai_boxing|kickboxing|judo|karate|taekwondo|wrestling|jiu_jitsu|brazilian_jiu_jitsu|bjj|krav_maga"
    q = (f'[out:json][timeout:30];(nwr["sport"~"{sp}"](around:{r},{lat},{lon});'
         f'nwr["amenity"="dojo"](around:{r},{lat},{lon}););out center tags 600;')
    payload = urllib.parse.urlencode({"data": q}).encode()
    data = None
    for ep in OVERPASS:
        try:
            with urllib.request.urlopen(urllib.request.Request(ep, data=payload, headers={"User-Agent": UA}), timeout=45) as resp:
                data = json.loads(resp.read().decode())
                break
        except Exception:
            continue
    if data is None:
        return 0
    n = 0
    with tx() as c:
        for el in data.get("elements", []):
            t = el.get("tags", {})
            name = (t.get("name") or "").strip()
            if not name:
                continue
            if el.get("type") == "node":
                la, lo = el.get("lat"), el.get("lon")
            else:
                ctr = el.get("center") or {}
                la, lo = ctr.get("lat"), ctr.get("lon")
            if la is None or lo is None:
                continue
            street = f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip()
            addr = ", ".join(x for x in (street, t.get('addr:postcode', ''), t.get('addr:city', '')) if x)[:200]
            vals = (name[:120], la, lo, addr, (t.get("addr:city") or "")[:80],
                    _clean_url(t.get("website") or t.get("contact:website") or ""),
                    (t.get("phone") or t.get("contact:phone") or "")[:40], json.dumps(_osm_sports(t)))
            oid = f"{el['type']}/{el['id']}"
            c.execute("INSERT OR IGNORE INTO gyms(name,lat,lon,address,city,website,phone,sports,osm_id,source,created_at)"
                      " VALUES(?,?,?,?,?,?,?,?,?,'osm',?)", (*vals, oid, now_iso()))
            n += 1
        c.execute("INSERT OR REPLACE INTO osm_cache(key,fetched_at,n) VALUES(?,?,?)", (key, now_iso(), n))
    return n


def _gym_dict(r):
    d = dict(r)
    d["sports"] = json.loads(d["sports"] or "[]")
    return d


def get_gym(gid):
    if not gid:
        return None
    with conn() as c:
        r = c.execute("SELECT * FROM gyms WHERE id=?", (gid,)).fetchone()
    return _gym_dict(r) if r else None


def gyms_near(lat, lon, radius_km=15, sports=None, pt_only=False, q=""):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.1))
    with conn() as c:
        rows = c.execute("SELECT * FROM gyms WHERE suspended=0 AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                         (lat - dlat, lat + dlat, lon - dlon, lon + dlon)).fetchall()
    out = []
    for r in rows:
        d = _gym_dict(r)
        d["distance_km"] = haversine_km(lat, lon, d["lat"], d["lon"])
        if d["distance_km"] > radius_km:
            continue
        if q and q.lower() not in f"{d['name']} {d['city']} {d['address']}".lower():
            continue
        if sports and not set(sports) & set(d["sports"]):
            continue
        if pt_only and d["pt_status"] != "yes":
            continue
        out.append(d)
    out.sort(key=lambda d: (d["pt_status"] != "yes", d["distance_km"]))
    return out


def gyms_all(sports=None, pt_only=False, q=""):
    with conn() as c:
        rows = c.execute("SELECT * FROM gyms WHERE suspended=0 ORDER BY id DESC LIMIT 500").fetchall()
    out = []
    for r in rows:
        d = _gym_dict(r)
        if q and q.lower() not in f"{d['name']} {d['city']} {d['address']}".lower():
            continue
        if sports and not set(sports) & set(d["sports"]):
            continue
        if pt_only and d["pt_status"] != "yes":
            continue
        out.append(d)
    return out


def _logo(logo):
    if not logo:
        return None
    name, blob = logo
    if len(blob) > 3 * 1024 * 1024:
        raise StrykeError("Logo kan ikke være større enn 3 MB.")
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(blob))
        im.load()
        im.thumbnail((256, 256))
        buf = io.BytesIO()
        im.convert("RGBA").save(buf, "PNG")
    except Exception:
        raise StrykeError("Kunne ikke lese bildefilen.")
    return base64.b64encode(buf.getvalue()).decode(), "image/png"


def _gym_fields(d):
    name = d["name"].strip()
    if len(name) < 2:
        raise StrykeError("Skriv inn gymmets navn.")
    sports = [s for s in d["sports"] if s in GYM_SPORTS]
    pt = d.get("pt_status", "unknown")
    price = int(d.get("price") or 0)
    cur = d.get("currency", "NOK")
    if pt != "yes":
        price = 0
    return {"name": name[:120], "address": (d.get("address") or "").strip()[:200], "city": (d.get("city") or "").strip()[:80],
            "website": _clean_url(d.get("website")), "phone": (d.get("phone") or "").strip()[:40], "email": (d.get("email") or "").strip()[:120],
            "sports": json.dumps(sports), "description": (d.get("description") or "").strip()[:1000],
            "pt_status": pt, "pt_price_cents": price * 100 if price else None, "currency": cur if price else ""}


def create_gym(uid, d, logo=None):
    f = _gym_fields(d)
    lg = _logo(logo)
    g = geocode(f"{f['address']}, {f['city']}")
    lat, lon, country = (g["lat"], g["lon"], g["country"]) if g else (60.0, 10.0, "NO")
    with tx() as c:
        cur = c.execute(
            "INSERT INTO gyms(name,lat,lon,address,city,country,website,phone,email,sports,description,logo_b64,logo_mime,"
            "pt_status,pt_price_cents,currency,owner_id,claim_status,source,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'approved','user',?)",
            (f["name"], lat, lon, f["address"], f["city"], country, f["website"], f["phone"], f["email"], f["sports"],
             f["description"], lg[0] if lg else "", lg[1] if lg else "", f["pt_status"], f["pt_price_cents"], f["currency"],
             uid, now_iso()))
        return cur.lastrowid


def update_gym(uid, gid, d, logo=None, remove_logo=False):
    old = get_gym(gid)
    if not old or old["owner_id"] != uid:
        raise PermissionError("Du eier ikke dette gymmet.")
    f = _gym_fields(d)
    lg = _logo(logo)
    if lg:
        f["logo_b64"], f["logo_mime"] = lg
    elif remove_logo:
        f["logo_b64"], f["logo_mime"] = "", ""
    with tx() as c:
        c.execute(f"UPDATE gyms SET {', '.join(k + '=?' for k in f)} WHERE id=? AND owner_id=?", (*f.values(), gid, uid))


def user_gyms(uid):
    with conn() as c:
        return [_gym_dict(r) for r in c.execute("SELECT * FROM gyms WHERE owner_id=? ORDER BY id DESC", (uid,))]
