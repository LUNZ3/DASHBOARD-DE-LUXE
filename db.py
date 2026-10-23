"""Cornerstone Combat Club - data layer.

SQLite storage for combat-sports gyms worldwide, plus:
  * a hand-picked seed of world-famous fight gyms
  * live import of EVERY combat gym OpenStreetMap knows about, city by city (Overpass API)
  * geocoding (Nominatim), favourites, reviews, PT confirmations and gym submissions
"""
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timezone

import requests

DB_PATH = os.environ.get("CCC_DB", "cornerstone.db")
UA = {"User-Agent": "CornerstoneCombatClub/1.0 (gym finder; contact: hello@cornerstone.club)"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

SPORTS = ["Boxing", "MMA", "Muay Thai", "Kickboxing", "Brazilian Jiu-Jitsu", "Wrestling",
          "Judo", "Karate", "Taekwondo", "Krav Maga", "Martial arts"]

# OSM sport=* values -> our labels
OSM_SPORT = {
    "boxing": "Boxing", "mma": "MMA", "mixed_martial_arts": "MMA", "muay_thai": "Muay Thai",
    "kickboxing": "Kickboxing", "brazilian_jiu_jitsu": "Brazilian Jiu-Jitsu", "bjj": "Brazilian Jiu-Jitsu",
    "jiu-jitsu": "Brazilian Jiu-Jitsu", "jiu_jitsu": "Brazilian Jiu-Jitsu", "wrestling": "Wrestling",
    "judo": "Judo", "karate": "Karate", "taekwondo": "Taekwondo", "krav_maga": "Krav Maga",
    "martial_arts": "Martial arts", "sambo": "Martial arts", "kung_fu": "Martial arts",
}
NAME_HINTS = [(r"muay|thai box", "Muay Thai"), (r"\bmma\b|mixed martial|fight team|top team", "MMA"),
              (r"box", "Boxing"), (r"kick", "Kickboxing"), (r"jiu|bjj|gracie", "Brazilian Jiu-Jitsu"),
              (r"wrestl", "Wrestling"), (r"judo", "Judo"), (r"karate", "Karate"), (r"krav", "Krav Maga")]

SCHEMA = """
CREATE TABLE IF NOT EXISTS gyms(
  id INTEGER PRIMARY KEY, osm_id TEXT UNIQUE, name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
  city TEXT DEFAULT '', country TEXT DEFAULT '', address TEXT DEFAULT '', website TEXT DEFAULT '',
  phone TEXT DEFAULT '', instagram TEXT DEFAULT '', sports TEXT NOT NULL DEFAULT '[]',
  description TEXT DEFAULT '', logo_url TEXT DEFAULT '',
  pt TEXT NOT NULL DEFAULT 'unknown' CHECK(pt IN ('unknown','yes','no')),
  pt_votes_yes INTEGER NOT NULL DEFAULT 0, pt_votes_no INTEGER NOT NULL DEFAULT 0,
  featured INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_geo ON gyms(lat, lon);
CREATE TABLE IF NOT EXISTS favourites(device TEXT NOT NULL, gym_id INTEGER NOT NULL, PRIMARY KEY(device, gym_id));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, gym_id INTEGER NOT NULL, author TEXT NOT NULL,
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), text TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(key TEXT PRIMARY KEY, label TEXT, n INTEGER, fetched_at TEXT);
"""

# Famous fight gyms. Coordinates are approximate (neighbourhood level) - verify before visiting.
# PT = private / personal training is publicly advertised by these gyms; always confirm with the gym.
SEED = [
    ("Tiger Muay Thai", 7.8436, 98.3236, "Phuket", "TH", "https://www.tigermuaythai.com", ["Muay Thai", "MMA", "Boxing", "Brazilian Jiu-Jitsu"], "The legendary Soi Ta-iad fight camp - privates with Thai trainers daily."),
    ("Phuket Top Team", 7.8460, 98.3340, "Phuket", "TH", "https://www.phukettopteam.com", ["MMA", "Muay Thai", "Brazilian Jiu-Jitsu"], "Full-time MMA camp with private sessions."),
    ("Bangtao Muay Thai & MMA", 7.9960, 98.2950, "Phuket", "TH", "https://www.bangtaomuaythai.com", ["Muay Thai", "MMA", "Boxing"], "Luxury fight resort on Bang Tao beach."),
    ("Fairtex Training Center", 12.9496, 100.8878, "Pattaya", "TH", "https://www.fairtextrainingcenter.com", ["Muay Thai", "MMA", "Boxing"], "Iconic Fairtex camp with hotel and privates."),
    ("Sitmonchai Gym", 14.0228, 99.5328, "Kanchanaburi", "TH", "https://www.sitmonchaigym.com", ["Muay Thai"], "Old-school countryside camp producing stadium fighters."),
    ("YOKKAO Training Center", 13.7230, 100.5800, "Bangkok", "TH", "https://www.yokkao.com", ["Muay Thai"], "Bangkok home of the YOKKAO brand."),
    ("Evolve MMA", 1.2847, 103.8510, "Singapore", "SG", "https://evolve-mma.com", ["MMA", "Muay Thai", "Boxing", "Brazilian Jiu-Jitsu"], "Asia's premier martial arts academy - world champion instructors."),
    ("City Kickboxing", -36.8670, 174.7700, "Auckland", "NZ", "https://www.citykickboxing.co.nz", ["Kickboxing", "MMA", "Brazilian Jiu-Jitsu"], "Home of multiple UFC champions."),
    ("Jackson Wink MMA", 35.0844, -106.6504, "Albuquerque", "US", "https://www.jacksonwinkmma.com", ["MMA", "Kickboxing", "Brazilian Jiu-Jitsu"], "One of the most decorated MMA camps on earth."),
    ("American Top Team", 26.2517, -80.1789, "Coconut Creek", "US", "https://www.americantopteam.com", ["MMA", "Boxing", "Brazilian Jiu-Jitsu", "Wrestling"], "Massive Florida HQ with an army of pros."),
    ("American Kickboxing Academy", 37.3496, -121.9046, "San Jose", "US", "https://www.akakickboxing.com", ["MMA", "Kickboxing", "Wrestling", "Brazilian Jiu-Jitsu"], "AKA - wrestling-heavy champion factory."),
    ("Kings MMA", 33.7313, -118.0020, "Huntington Beach", "US", "https://www.kingsmma.com", ["MMA", "Muay Thai", "Brazilian Jiu-Jitsu"], "Rafael Cordeiro's striking powerhouse."),
    ("Xtreme Couture", 36.1215, -115.2016, "Las Vegas", "US", "https://www.xtremecouture.com", ["MMA", "Boxing", "Brazilian Jiu-Jitsu", "Wrestling"], "Randy Couture's Vegas fight gym."),
    ("Syndicate MMA", 36.0651, -115.2414, "Las Vegas", "US", "https://www.syndicatemma.com", ["MMA", "Brazilian Jiu-Jitsu", "Kickboxing"], "John Wood's Vegas pro team."),
    ("Team Alpha Male", 38.5816, -121.4944, "Sacramento", "US", "https://www.teamalphamale.com", ["MMA", "Wrestling", "Brazilian Jiu-Jitsu"], "Urijah Faber's Sacramento squad."),
    ("Elevation Fight Team", 39.7392, -104.9903, "Denver", "US", "https://www.elevationfightteam.com", ["MMA", "Brazilian Jiu-Jitsu"], "High-altitude MMA camp."),
    ("Factory X", 39.6478, -104.9878, "Englewood", "US", "https://www.factoryxmuaythai.com", ["Muay Thai", "MMA", "Boxing"], "Marc Montoya's striking hub."),
    ("Renzo Gracie Academy", 40.7505, -73.9934, "New York", "US", "https://www.renzogracieacademy.com", ["Brazilian Jiu-Jitsu", "MMA", "Muay Thai"], "Manhattan BJJ institution."),
    ("Gleason's Gym", 40.7037, -73.9897, "New York", "US", "https://www.gleasonsgym.net", ["Boxing"], "America's oldest active boxing gym - every trainer offers privates."),
    ("Wild Card Boxing Club", 34.0981, -118.3270, "Los Angeles", "US", "https://www.wildcardboxing.com", ["Boxing"], "Freddie Roach's Hollywood boxing gym."),
    ("Gracie Barra HQ", 33.6846, -117.8265, "Irvine", "US", "https://www.graciebarra.com", ["Brazilian Jiu-Jitsu"], "Global BJJ network headquarters."),
    ("Tristar Gym", 45.5306, -73.6090, "Montreal", "CA", "https://www.tristargym.com", ["MMA", "Brazilian Jiu-Jitsu", "Kickboxing", "Wrestling"], "Firas Zahabi's world-famous Montreal gym."),
    ("SBG Ireland", 53.3392, -6.2954, "Dublin", "IE", "https://www.sbgireland.com", ["MMA", "Brazilian Jiu-Jitsu", "Boxing"], "John Kavanagh's Straight Blast Gym."),
    ("London Shootfighters", 51.5366, -0.1043, "London", "GB", "https://www.londonshootfighters.com", ["MMA", "Brazilian Jiu-Jitsu", "Wrestling", "Muay Thai"], "UK MMA pioneers in Islington."),
    ("Allstars Training Center", 59.3326, 18.0230, "Stockholm", "SE", "https://www.allstarstc.se", ["MMA", "Kickboxing", "Brazilian Jiu-Jitsu", "Boxing"], "Scandinavia's elite MMA camp."),
    ("Mike's Gym", 52.3584, 4.8622, "Amsterdam", "NL", "https://www.mikesgym.nl", ["Kickboxing", "Boxing"], "Dutch kickboxing legend factory."),
    ("Hemmers Gym", 51.5719, 4.7683, "Breda", "NL", "https://www.hemmersgym.com", ["Kickboxing"], "Home of Dutch-style K-1 champions."),
    ("Golden Glory", 51.5890, 4.7760, "Breda", "NL", "https://www.goldenglory.nl", ["Kickboxing", "MMA"], "Historic kickboxing and MMA team."),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def domain(url):
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return urllib.parse.urlparse(url).netloc.replace("www.", "")


def logo_for(url):
    """Logo via the site's own favicon/touch icon (served through Google's icon CDN)."""
    d = domain(url)
    return f"https://www.google.com/s2/favicons?domain={d}&sz=128" if d else ""


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM gyms WHERE source='seed'").fetchone()[0] == 0:
            for n, lat, lon, city, cc, web, sp, desc in SEED:
                c.execute("""INSERT OR IGNORE INTO gyms(osm_id,name,lat,lon,city,country,website,sports,description,
                             logo_url,pt,featured,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,'yes',1,'seed',?)""",
                          ("seed:" + hashlib.md5(n.encode()).hexdigest()[:10], n, lat, lon, city, cc, web,
                           json.dumps(sp), desc, logo_for(web), now()))


# ------------------------------------------------------------------ queries
def _row(r):
    d = dict(r)
    d["sports"] = json.loads(d["sports"] or "[]")
    return d


def gyms(q="", sports=None, pt_only=False, country="", featured_only=False, limit=5000):
    sql, args = "SELECT g.*, (SELECT ROUND(AVG(rating),1) FROM reviews r WHERE r.gym_id=g.id) avg_rating, " \
                "(SELECT COUNT(*) FROM reviews r WHERE r.gym_id=g.id) n_reviews FROM gyms g WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR city LIKE ? OR address LIKE ?)"
        args += [f"%{q}%"] * 3
    if pt_only:
        sql += " AND pt='yes'"
    if country:
        sql += " AND country=?"
        args.append(country)
    if featured_only:
        sql += " AND featured=1"
    sql += " ORDER BY featured DESC, name LIMIT ?"
    args.append(limit)
    with conn() as c:
        rows = [_row(r) for r in c.execute(sql, args)]
    if sports:
        rows = [r for r in rows if set(sports) & set(r["sports"])]
    return rows


def gym(gid):
    rows = [g for g in gyms(limit=100000) if g["id"] == gid]
    return rows[0] if rows else None


def countries():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT country FROM gyms WHERE country<>'' ORDER BY 1")]


def stats():
    with conn() as c:
        one = lambda s: c.execute(s).fetchone()[0]
        return {"gyms": one("SELECT COUNT(*) FROM gyms"), "pt": one("SELECT COUNT(*) FROM gyms WHERE pt='yes'"),
                "countries": one("SELECT COUNT(DISTINCT country) FROM gyms WHERE country<>''"),
                "cities": one("SELECT COUNT(*) FROM imports")}


def haversine_km(a, b, c, d):
    p = math.pi / 180
    h = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def nearest(lat, lon, n=10, **filters):
    rows = gyms(**filters)
    for r in rows:
        r["km"] = haversine_km(lat, lon, r["lat"], r["lon"])
    return sorted(rows, key=lambda r: r["km"])[:n]


# ------------------------------------------------------------------ community
def add_gym(name, lat, lon, city, country, website, sports, description, pt, address="", phone="", instagram=""):
    if not name.strip():
        raise ValueError("Name is required")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordinates out of range")
    with conn() as c:
        c.execute("""INSERT INTO gyms(name,lat,lon,city,country,address,website,phone,instagram,sports,description,
                     logo_url,pt,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'user',?)""",
                  (name.strip(), lat, lon, city, country.upper()[:2], address, website, phone, instagram,
                   json.dumps(sports), description, logo_for(website), pt, now()))


def vote_pt(gid, yes):
    col = "pt_votes_yes" if yes else "pt_votes_no"
    with conn() as c:
        c.execute(f"UPDATE gyms SET {col}={col}+1 WHERE id=?", (gid,))
        y, n, cur = c.execute("SELECT pt_votes_yes, pt_votes_no, pt FROM gyms WHERE id=?", (gid,)).fetchone()
        # community decides once there's a clear signal (seeded gyms stay 'yes' unless clearly outvoted)
        if y >= 2 and y > n:
            c.execute("UPDATE gyms SET pt='yes' WHERE id=?", (gid,))
        elif n >= 3 and n > y * 2:
            c.execute("UPDATE gyms SET pt='no' WHERE id=?", (gid,))


def toggle_fav(device, gid):
    with conn() as c:
        if c.execute("SELECT 1 FROM favourites WHERE device=? AND gym_id=?", (device, gid)).fetchone():
            c.execute("DELETE FROM favourites WHERE device=? AND gym_id=?", (device, gid))
            return False
        c.execute("INSERT INTO favourites VALUES(?,?)", (device, gid))
        return True


def fav_ids(device):
    with conn() as c:
        return {r[0] for r in c.execute("SELECT gym_id FROM favourites WHERE device=?", (device,))}


def add_review(gid, author, rating, text):
    with conn() as c:
        c.execute("INSERT INTO reviews(gym_id,author,rating,text,created_at) VALUES(?,?,?,?,?)",
                  (gid, (author or "Anonymous fighter")[:40], int(rating), text[:1000], now()))


def reviews(gid):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM reviews WHERE gym_id=? ORDER BY id DESC", (gid,))]


# ------------------------------------------------------------------ OpenStreetMap import
def geocode(place):
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": place, "format": "json", "limit": 1, "addressdetails": 1}, headers=UA, timeout=20)
    r.raise_for_status()
    js = r.json()
    if not js:
        raise ValueError(f"Couldn't find '{place}'")
    h = js[0]
    bb = [float(x) for x in h["boundingbox"]]  # s, n, w, e
    cc = (h.get("address", {}).get("country_code") or "").upper()
    return {"lat": float(h["lat"]), "lon": float(h["lon"]), "bbox": bb, "label": h["display_name"], "cc": cc}


def _sports_from_tags(t):
    found = [OSM_SPORT[s.strip()] for s in (t.get("sport") or "").replace(",", ";").split(";") if s.strip() in OSM_SPORT]
    name = (t.get("name") or "").lower()
    for pat, label in NAME_HINTS:
        if re.search(pat, name):
            found.append(label)
    return sorted(set(found)) or ["Martial arts"]


def import_osm(place, radius_km=25):
    """Pull every combat-sports gym OSM knows around a place. Returns (n_new, label)."""
    g = geocode(place)
    key = f"{round(g['lat'], 2)},{round(g['lon'], 2)},{radius_km}"
    r_m = int(radius_km * 1000)
    sports_re = "|".join(k for k in OSM_SPORT)
    ql = f"""[out:json][timeout:50];
(
  nwr["sport"~"{sports_re}"](around:{r_m},{g['lat']},{g['lon']});
  nwr["leisure"~"fitness_centre|sports_centre|dojo"]["name"~"box|mma|muay|thai|kick|jiu|bjj|grappl|fight|combat|martial|wrestl|dojo|krav",i](around:{r_m},{g['lat']},{g['lon']});
  nwr["amenity"="dojo"](around:{r_m},{g['lat']},{g['lon']});
);
out center tags;"""
    data, err = None, None
    for url in OVERPASS:
        try:
            resp = requests.post(url, data={"data": ql}, headers=UA, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:  # try the mirror
            err = e
            time.sleep(1)
    if data is None:
        raise RuntimeError(f"OpenStreetMap is busy, try again in a minute ({err})")

    new = 0
    with conn() as c:
        for el in data.get("elements", []):
            t = el.get("tags", {})
            name = t.get("name")
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if not name or lat is None:
                continue
            web = t.get("website") or t.get("contact:website") or t.get("url") or ""
            addr = " ".join(x for x in [t.get("addr:street", ""), t.get("addr:housenumber", "")] if x).strip()
            city = t.get("addr:city") or place.split(",")[0].title()
            ig = t.get("contact:instagram", "")
            pt = "yes" if re.search(r"personal|private|\bpt\b", " ".join(t.values()).lower()) else "unknown"
            cur = c.execute("""INSERT OR IGNORE INTO gyms(osm_id,name,lat,lon,city,country,address,website,phone,instagram,
                     sports,description,logo_url,pt,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'osm',?)""",
                            (f"{el['type']}/{el['id']}", name, lat, lon, city, g["cc"], addr, web,
                             t.get("phone") or t.get("contact:phone", ""), ig, json.dumps(_sports_from_tags(t)),
                             t.get("description", ""), logo_for(web), pt, now()))
            new += cur.rowcount
        c.execute("INSERT OR REPLACE INTO imports VALUES(?,?,?,?)", (key, g["label"], new, now()))
    return new, g


def imports():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM imports ORDER BY fetched_at DESC")]
