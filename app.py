"""STRYKE - Find your coach. Train like a fighter.  (Streamlit app, single file: app.py + db.py)"""
import hashlib
import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

import db

# ------------------------------------------------------------------ theme
ACCENT = "#00D1FF"  # electric blue. Try #D4FF00 (volt lime) or #FF2E63 (electric red)

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;900&display=swap');
:root {{ --acc:{ACCENT}; --bg:#0A0A0B; --card:#141416; --line:#26262A; --mut:#9A9AA3; }}
html, body, [class*="css"] {{ font-family:'Inter',sans-serif; }}
.stApp {{ background:var(--bg); }}
#MainMenu, footer, header[data-testid="stHeader"] {{ visibility:hidden; height:0; }}
.block-container {{ padding-top:1.2rem; max-width:1180px; }}
h1,h2,h3 {{ font-weight:900 !important; letter-spacing:-0.02em; }}
.brand {{ font-weight:900; font-size:1.7rem; letter-spacing:.12em; color:#fff; }}
.brand b {{ color:var(--acc); }}
.hero {{ padding:4.5rem 2rem 4rem; margin:1rem 0 1.5rem; border:1px solid var(--line); border-radius:24px;
  background: radial-gradient(900px 400px at 85% -10%, rgba(0,209,255,.22), transparent 60%),
              radial-gradient(600px 300px at 0% 110%, rgba(0,209,255,.10), transparent 60%), #0E0E10; }}
.hero h1 {{ font-size:clamp(2.4rem,7vw,4.6rem); line-height:1.02; margin:0 0 1rem; color:#fff; }}
.hero h1 em {{ font-style:normal; color:var(--acc); }}
.hero p {{ color:var(--mut); font-size:1.15rem; max-width:560px; }}
.chip {{ display:inline-block; padding:.35rem .8rem; margin:.2rem .25rem .2rem 0; border:1px solid var(--line);
  border-radius:999px; color:#ddd; font-size:.85rem; background:#101012; }}
.chip.acc {{ border-color:var(--acc); color:var(--acc); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:1.2rem 1.3rem; height:100%; transition:.15s; }}
.card:hover {{ border-color:var(--acc); transform:translateY(-2px); box-shadow:0 8px 30px rgba(0,209,255,.08); }}
.card h4 {{ margin:.2rem 0 .3rem; font-size:1.1rem; color:#fff; }}
.muted {{ color:var(--mut); font-size:.9rem; }}
.num {{ font-weight:900; font-size:2rem; color:var(--acc); }}
.avatar {{ width:56px; height:56px; border-radius:14px; display:flex; align-items:center; justify-content:center;
  font-weight:900; font-size:1.3rem; color:#000; background:var(--acc); float:left; margin-right:.9rem; }}
.badge-ok {{ color:#000; background:var(--acc); padding:.15rem .55rem; border-radius:6px; font-size:.75rem; font-weight:800; }}
.badge-demo {{ color:#FFB020; border:1px solid #FFB020; padding:.1rem .5rem; border-radius:6px; font-size:.72rem; font-weight:700; }}
.badge-no {{ color:var(--mut); border:1px solid var(--line); padding:.1rem .5rem; border-radius:6px; font-size:.72rem; }}
.banner {{ border:1px dashed #FFB020; color:#FFB020; border-radius:12px; padding:.7rem 1rem; font-size:.9rem; margin:.6rem 0; }}
.stButton>button, .stDownloadButton>button {{ border-radius:12px; font-weight:700; border:1px solid var(--line); }}
.stButton>button[kind="primary"] {{ background:var(--acc); color:#000; border:none; }}
.stButton>button:hover {{ border-color:var(--acc); color:var(--acc); }}
.stButton>button[kind="primary"]:hover {{ color:#000; filter:brightness(1.1); }}
.stButton>button:focus-visible, input:focus-visible {{ outline:2px solid var(--acc) !important; }}
@media (max-width:640px) {{ .hero {{ padding:2.5rem 1.2rem; }} .brand {{ font-size:1.3rem; }} }}
.stApp, .stApp p, .stApp label, .stApp span, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stMarkdown {{ color:#F5F5F7; }}
.stApp .muted, .stApp .card .muted, .stApp .hero p, .stApp .hero .muted {{ color:var(--mut); }}
.stApp .brand b, .stApp .num, .stApp .hero h1 em {{ color:var(--acc); }}
.stApp .chip.acc {{ color:var(--acc); }}
.stApp .avatar, .stApp .badge-ok {{ color:#000; }}
.stApp .badge-demo, .stApp .banner {{ color:#FFB020; }}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"], textarea, input {{ background:#141416 !important; color:#F5F5F7 !important; }}
[data-testid="stSidebar"], [data-testid="stForm"], [data-testid="stExpander"] {{ background:#0E0E10; border-color:var(--line); }}
.stButton>button {{ background:#141416; color:#F5F5F7; }}
.stButton>button[kind="primary"] {{ background:var(--acc); color:#000; }}
</style>
"""

st.set_page_config(page_title="STRYKE", page_icon="🥊", layout="wide")
db.init()
st.markdown(CSS, unsafe_allow_html=True)
ss = st.session_state
for k, v in {"page": "home", "uid": None, "coach_id": None, "origin": None, "gps_ask": False, "gym_id": None,
             "map_center": (59.9139, 10.7522), "map_label": "Oslo", "map_zoom": 11, "view_center": None,
             "last_fetch": None, "sel": None, "gps_map": False, "view_zoom": None}.items():
    ss.setdefault(k, v)

user = db.get_user(ss.uid)  # re-read every run so suspensions apply immediately
if ss.uid and not user:
    ss.uid = None
my_coach = db.coach_for_user(user["id"]) if user else None
e = html.escape


def nav(page, coach_id=None, gym_id=None):
    ss.page = page
    if coach_id is not None:
        ss.coach_id = coach_id
    if gym_id is not None:
        ss.gym_id = gym_id


def local(dt_utc, tz):
    return dt_utc.astimezone(ZoneInfo(tz))


def fmt_slot(dt_utc, tz):
    return local(dt_utc, tz).strftime("%a %d %b, %H:%M")


def initials(name):
    n = name.replace("Demo:", "").split()
    return "".join(p[0] for p in n[:2]).upper()


def badges(c):
    out = []
    if c["demo"]:
        out.append('<span class="badge-demo">DEMO PROFILE</span>')
    out.append('<span class="badge-ok">✓ VERIFIED</span>' if c["verified"] else '<span class="badge-no">Not verified</span>')
    return " ".join(out)


def stars(c):
    return f"★ {c['rating']:.1f} ({c['n_reviews']})" if c.get("rating") else "No reviews yet"


# ------------------------------------------------------------------ header
def header():
    cols = st.columns([1.8, 1, 1, 1.1, 1, 1.4])
    cols[0].markdown('<div class="brand">STRY<b>K</b>E</div>', unsafe_allow_html=True)
    cols[1].button("Find a coach", on_click=nav, args=("coaches",), use_container_width=True)
    cols[2].button("Gym map", on_click=nav, args=("gyms",), use_container_width=True, key="hg")
    cols[3].button("Become a coach", on_click=nav, args=("apply",), use_container_width=True)
    if user:
        cols[4].button("My bookings", on_click=nav, args=("dashboard",), use_container_width=True)
        lbl = user["name"].split()[0]
        cols[5].button(f"Account · {lbl}", on_click=nav, args=("account",), use_container_width=True)
    else:
        cols[4].write("")
        cols[5].button("Log in / Sign up", on_click=nav, args=("account",), type="primary", use_container_width=True)
    extra = [("List your gym", "gym_manage")]
    if my_coach:
        extra.append(("Coach dashboard", "coach_dash"))
    if db.is_admin(user):
        extra.append(("Admin", "admin"))
    ec = st.columns(len(extra) + 4)
    for i, (lbl, p) in enumerate(extra):
        ec[i].button(lbl, on_click=nav, args=(p,), key=f"x_{p}", use_container_width=True)


def coach_card(c, key, fav_ids=()):
    dist = f" · {c['distance_km']:.0f} km away" if c.get("distance_km") is not None else ""
    nxt = f"Next: {fmt_slot(c['next_slot'], c['tz'])}" if c.get("next_slot") else "No open slots (14 days)"
    chips = "".join(f'<span class="chip">{e(s)}</span>' for s in c["sports"])
    st.markdown(
        f'<div class="card"><div class="avatar">{e(initials(c["name"]))}</div>'
        f'<h4>{e(c["name"])}</h4><div class="muted">{e(c["city"])}, {e(c["country"])}{dist}</div>'
        f'<div style="margin:.5rem 0">{badges(c)}</div>{chips}'
        f'<div class="muted" style="margin-top:.6rem">{c["years_exp"]} yrs · {e(", ".join(c["languages"]))} · {stars(c)}</div>'
        f'<div class="muted">{e(nxt)}</div>'
        f'<div style="margin-top:.6rem;font-weight:800;font-size:1.2rem">{db.money(c["price_cents"], c["currency"])}'
        f' <span class="muted">/ {c["session_minutes"]} min</span></div></div>',
        unsafe_allow_html=True)
    st.button("View profile & book", key=f"v_{key}_{c['id']}", on_click=nav, args=("profile", c["id"]), use_container_width=True)


# -------------------------------------------------------------------- pages
def page_home():
    st.markdown(
        '<div class="hero"><div class="muted" style="letter-spacing:.2em;font-weight:700">COMBAT SPORTS · ONE-TO-ONE</div>'
        '<h1>Find your coach.<br><em>Train like a fighter.</em></h1>'
        '<p>Book experienced boxing, MMA, Muay Thai, kickboxing, BJJ and wrestling coaches near you. '
        'Compare real credentials, pick a time, train.</p></div>', unsafe_allow_html=True)
    a, b, b2, _ = st.columns([1, 1, 1, 2])
    a.button("Find a coach", type="primary", on_click=nav, args=("coaches",), use_container_width=True, key="h1")
    b.button("Open gym map", on_click=nav, args=("gyms",), use_container_width=True, key="h3")
    b2.button("Become a coach", on_click=nav, args=("apply",), use_container_width=True, key="h2")

    st.markdown("### Sports")
    st.markdown("".join(f'<span class="chip acc">{e(s)}</span>' for s in db.SPORTS) + '<span class="chip">+ more coming</span>',
                unsafe_allow_html=True)

    st.markdown("### How it works")
    c = st.columns(3)
    for col, (n, t, d) in zip(c, [("01", "Discover", "Search by sport, city, price, language and experience."),
                                  ("02", "Compare", "See documented credentials, verification status and reviews."),
                                  ("03", "Book", "Pick a real open slot in the coach's local time and confirm.")]):
        col.markdown(f'<div class="card"><div class="num">{n}</div><h4>{t}</h4><div class="muted">{d}</div></div>', unsafe_allow_html=True)

    st.markdown("### Why verified coaches matter")
    st.markdown(
        f'<div class="card"><div class="muted">A STRYKE ✓ badge is only shown after an administrator has reviewed a coach\'s '
        f'evidence (fight records, certificates, coaching history). Policy: at least {db.MIN_YEARS} years of documented '
        f'competitive experience with fights/achievements, <b>or</b> at least {db.MIN_YEARS} years of coaching. '
        f'Coaches cannot verify themselves.</div></div>', unsafe_allow_html=True)

    st.markdown("### Example coaches")
    st.markdown('<div class="banner">These are fictional DEMO profiles for illustration. They are not real people and are not verified.</div>',
                unsafe_allow_html=True)
    top = db.search_coaches(sort="Experience")[:3]
    for col, co in zip(st.columns(3), top):
        with col:
            coach_card(co, "home")


def page_coaches():
    st.markdown("## Find a coach")
    top = st.columns([2, 1.3, 1.3])
    q = top[0].text_input("Search", placeholder="Name, sport, style, city…")
    sports = top[1].multiselect("Sport", db.SPORTS)
    city = top[2].selectbox("Coach located in", ["Anywhere"] + list(db.CITIES))
    f = st.columns(5)
    max_price = f[0].slider("Max price / session", 20, 1000, 1000)
    min_years = f[1].slider("Min. experience (yrs)", 0, 20, 0)
    langs = sorted({l for c in db.search_coaches() for l in c["languages"]})
    language = f[2].selectbox("Language", ["Any"] + langs)
    min_rating = f[3].selectbox("Min. rating", [0, 3, 4, 4.5], format_func=lambda x: "Any" if x == 0 else f"{x}+")
    only_av = f[4].checkbox("Has open slots", value=False)

    st.markdown("##### Your location (for distance)")
    lc = st.columns([1.3, 1.5, 2])
    if lc[0].button("📍 Use my location (GPS)"):
        ss.gps_ask = True
    if ss.gps_ask:
        try:
            from streamlit_js_eval import get_geolocation
            g = get_geolocation()  # browser asks for permission here
            if g and "coords" in g:
                ss.origin = {"lat": g["coords"]["latitude"], "lon": g["coords"]["longitude"], "label": "your GPS position"}
                ss.gps_ask = False
            elif g and "error" in g:
                st.warning("Location permission denied or unavailable. Choose a city instead.")
                ss.gps_ask = False
            else:
                st.info("Waiting for browser location permission…")
        except Exception:
            st.warning("GPS component unavailable. Choose a city instead.")
            ss.gps_ask = False
    manual = lc[1].selectbox("…or choose your city", ["—"] + list(db.CITIES), label_visibility="visible")
    if manual != "—":
        la, lo = db.CITIES[manual][:2]
        ss.origin = {"lat": la, "lon": lo, "label": manual}
    if ss.origin:
        lc[2].caption(f"Distances measured from {ss.origin['label']}.")
    sort = st.selectbox("Sort by", ["Best match", "Distance", "Price (low to high)", "Rating", "Experience"])
    if sort == "Distance" and not ss.origin:
        st.info("Set your location above to sort by distance.")

    res = db.search_coaches(q, sports, "" if city == "Anywhere" else city, max_price, min_years,
                            "" if language == "Any" else language, min_rating, only_av, ss.origin, sort)
    st.caption(f"{len(res)} coach{'es' if len(res) != 1 else ''} found · see them on the interactive Gym map too")
    if not res:
        st.info("No coaches match these filters. Try widening them.")
    favs = db.favourite_ids(user["id"]) if user else set()
    for i in range(0, len(res), 3):
        for col, co in zip(st.columns(3), res[i:i + 3]):
            with col:
                coach_card(co, "list", favs)


def page_profile():
    c = db.get_coach(ss.coach_id)
    if not c:
        st.error("Coach not found.")
        return
    st.button("← Back to coaches", on_click=nav, args=("coaches",))
    st.markdown(f'<div class="avatar" style="width:84px;height:84px;font-size:2rem">{e(initials(c["name"]))}</div>'
                f'<h1 style="margin:0">{e(c["name"])}</h1>'
                f'<div class="muted">{e(c["city"])}, {e(c["country"])} · timezone {e(c["tz"])}</div>'
                f'<div style="margin:.5rem 0 1rem">{badges(c)}</div>', unsafe_allow_html=True)
    if c["demo"]:
        st.markdown('<div class="banner">Demo content: this coach is fictional and all credentials below are illustrative only.</div>', unsafe_allow_html=True)
    left, right = st.columns([2, 1.2])
    with left:
        st.markdown("".join(f'<span class="chip acc">{e(s)}</span>' for s in c["sports"]), unsafe_allow_html=True)
        st.markdown(f"**Coaching style:** {e(c['style'] or '—')}")
        st.markdown(f"**Languages:** {e(', '.join(c['languages']))} · **Experience:** {c['years_exp']} years")
        st.write(c["bio"] or "")
        st.markdown("### Credentials")
        st.caption("Verified = reviewed by a STRYKE administrator. Otherwise these are self-reported by the coach." if not c["verified"]
                   else "This coach's evidence was reviewed and approved by a STRYKE administrator.")
        st.markdown(f"**Fight record:** {e(c['record'] or '—')}")
        st.markdown(f"**Achievements & belts:** {e(c['achievements'] or '—')}")
        st.markdown(f"**Qualifications:** {e(c['qualifications'] or '—')}")
        st.markdown("### Customer reviews")
        st.caption("Reviews come only from customers who completed a session. They are separate from competitive achievements.")
        revs = db.reviews_for(c["id"])
        if not revs:
            st.info("No reviews yet.")
        for r in revs:
            st.markdown(f'<div class="card"><b>{"★" * r["rating"]}{"☆" * (5 - r["rating"])}</b> · {e(r["name"].split()[0])}'
                        f'<div class="muted">{e(r["text"])}</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown(f'<div class="card"><div class="num">{db.money(c["price_cents"], c["currency"])}</div>'
                    f'<div class="muted">per {c["session_minutes"]}-minute one-to-one session</div></div>', unsafe_allow_html=True)
        if user:
            is_fav = c["id"] in db.favourite_ids(user["id"])
            if st.button("♥ Saved" if is_fav else "♡ Save coach", use_container_width=True):
                db.toggle_favourite(user["id"], c["id"])
                st.rerun()
        else:
            st.caption("Log in to save favourites.")
        slots = db.free_slots(c["id"])
        st.markdown("#### Availability")
        if not slots:
            st.info("No open slots in the next 14 days.")
        else:
            st.caption(f"Times shown in {c['city']} local time ({c['tz']}).")
            pick = st.selectbox("Choose a time", slots, format_func=lambda s: fmt_slot(s, c["tz"]))
            pb = db.price_breakdown(c)
            st.markdown(f"Session: **{db.money(pb['price'], pb['currency'])}**  \n"
                        f"<span class='muted'>of which platform fee {pb['pct']:g}% = {db.money(pb['fee'], pb['currency'])}; "
                        f"coach receives {db.money(pb['coach_gets'], pb['currency'])}</span>", unsafe_allow_html=True)
            st.caption(f"Cancellation: free up to {db.FREE_CANCEL_HOURS} h before start; later cancellations are not refunded.")
            note = st.text_input("Note / training location (optional)", max_chars=200)
            st.markdown('<div class="banner">TEST MODE: no payment provider is connected. Booking is recorded, but no money is charged or moved.</div>',
                        unsafe_allow_html=True)
            if not user:
                st.button("Log in to book", on_click=nav, args=("account",), type="primary", use_container_width=True)
            elif my_coach and my_coach["id"] == c["id"]:
                st.info("You can't book yourself.")
            elif st.button("Confirm booking (test mode)", type="primary", use_container_width=True):
                try:
                    db.create_booking(user["id"], c["id"], pick, note)
                    st.success("Booking confirmed (test mode, no payment taken). See My bookings.")
                except db.SlotTaken as ex:
                    st.error(str(ex))
                except db.StrykeError as ex:
                    st.error(str(ex))


def page_account():
    if user:
        st.markdown(f"## {e(user['name'])}")
        st.write(user["email"])
        if st.button("Log out"):
            ss.uid = None
            nav("home")
            st.rerun()
        return
    st.markdown("## Account")
    st.caption("Accounts are stored in this app's database (SQLite). Email addresses are not verified yet.")
    t1, t2 = st.tabs(["Log in", "Sign up"])
    with t1:
        with st.form("login"):
            em = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                try:
                    ss.uid = db.login(em, pw)
                    nav("home")
                    st.rerun()
                except db.StrykeError as ex:
                    st.error(str(ex))
    with t2:
        with st.form("signup"):
            nm = st.text_input("Name")
            em = st.text_input("Email", key="se")
            pw = st.text_input("Password (min 8 chars)", type="password", key="sp")
            if st.form_submit_button("Create account", type="primary"):
                try:
                    ss.uid = db.register(em, nm, pw)
                    nav("home")
                    st.rerun()
                except db.StrykeError as ex:
                    st.error(str(ex))


def page_dashboard():
    if not user:
        st.info("Log in to see your bookings.")
        return
    st.markdown("## My bookings")
    bs = db.user_bookings(user["id"])
    now = datetime.now(timezone.utc)
    up = [b for b in bs if b["status"] in db.ACTIVE and db._p(b["start_utc"]) >= now]
    past = [b for b in bs if b not in up]
    st.markdown("### Upcoming")
    if not up:
        st.info("No upcoming sessions. Find a coach to get started.")
        st.button("Find a coach", on_click=nav, args=("coaches",), key="d1")
    for b in up:
        with st.container(border=True):
            st.markdown(f"**{e(b['coach_name'])}** · {fmt_slot(db._p(b['start_utc']), b['tz'])} ({e(b['tz'])})")
            st.caption(f"Status: {b['status']} · Payment: {b['payment_status'].replace('_', ' ')} · {db.money(b['price_cents'], b['currency'])}")
            if st.button("Cancel booking", key=f"c{b['id']}"):
                try:
                    ok = db.cancel_booking(user["id"], b["id"])
                    st.success("Cancelled. " + ("Free cancellation." if ok else "Late cancellation: no refund per policy."))
                    st.rerun()
                except (db.StrykeError, PermissionError) as ex:
                    st.error(str(ex))
    st.markdown("### Past")
    if not past:
        st.caption("Nothing yet.")
    for b in past:
        with st.container(border=True):
            st.markdown(f"**{e(b['coach_name'])}** · {fmt_slot(db._p(b['start_utc']), b['tz'])} · {b['status']}")
            if b["status"] == "completed" and not b["reviewed"]:
                with st.form(f"r{b['id']}"):
                    rt = st.slider("Rating", 1, 5, 5)
                    tx = st.text_area("Your review", max_chars=1000)
                    if st.form_submit_button("Submit review"):
                        try:
                            db.add_review(user["id"], b["id"], rt, tx)
                            st.rerun()
                        except db.StrykeError as ex:
                            st.error(str(ex))
    st.markdown("### Saved coaches")
    favs = db.favourite_ids(user["id"])
    if not favs:
        st.caption("No saved coaches yet.")
    for cid in favs:
        co = db.get_coach(cid)
        st.button(f"♥ {co['name']}", key=f"f{cid}", on_click=nav, args=("profile", cid))


def page_apply():
    st.markdown("## Become a coach")
    st.markdown(f'<div class="card"><b>Eligibility policy.</b> <span class="muted">At least {db.MIN_YEARS} years of documented '
                f'combat-sports experience with fights/achievements, <b>or</b> at least {db.MIN_YEARS} years of relevant coaching '
                f'experience. Every application is reviewed by a STRYKE administrator and needs supporting evidence. '
                f'Nobody is approved automatically.</span></div>', unsafe_allow_html=True)
    if not user:
        st.info("Log in or create an account to apply.")
        st.button("Log in / Sign up", on_click=nav, args=("account",), key="ap1")
        return
    app = db.get_application(user["id"])
    if app:
        st.markdown(f"**Your application status: `{app['status'].replace('_', ' ')}`**")
        if app["admin_note"]:
            st.warning(f"Note from reviewer: {app['admin_note']}")
        if app["status"] in ("submitted", "under_review", "approved"):
            return
    with st.form("apply"):
        d = (app or {}).get("data", {})
        c1, c2 = st.columns(2)
        full = c1.text_input("Full name", d.get("full_name", user["name"]))
        phone = c2.text_input("Phone", d.get("phone", ""))
        city = c1.selectbox("City / service area", list(db.CITIES))
        price = c2.number_input("Price per 60-min session (local currency)", 10, 5000, int(d.get("price", 400)))
        sports = st.multiselect("Sports", db.SPORTS, d.get("sports", []))
        langs = st.multiselect("Languages", ["English", "Norwegian", "Swedish", "Danish", "German", "Spanish", "Thai", "Dutch"], d.get("languages", ["English"]))
        style = st.text_input("Coaching style", d.get("style", ""))
        bio = st.text_area("Biography", d.get("bio", ""))
        c3, c4 = st.columns(2)
        fy = c3.number_input("Years of competitive experience", 0, 60, int(d.get("fight_years", 0)))
        cy = c4.number_input("Years of coaching experience", 0, 60, int(d.get("coaching_years", 0)))
        rec = st.text_input("Fight record", d.get("record", ""))
        ach = st.text_area("Competition achievements & belts", d.get("achievements", ""))
        qual = st.text_area("Qualifications & coaching history", d.get("qualifications", ""))
        files = st.file_uploader("Evidence (PDF/JPG/PNG, private, only admins can view)", accept_multiple_files=True,
                                 type=["pdf", "jpg", "jpeg", "png"])
        if st.form_submit_button("Submit application", type="primary"):
            try:
                db.submit_application(user["id"], dict(full_name=full, phone=phone, city=city, sports=sports, languages=langs,
                                                       bio=bio, price=price, style=style, fight_years=int(fy), coaching_years=int(cy),
                                                       record=rec, achievements=ach, qualifications=qual),
                                      [(f.name, f.getvalue()) for f in files])
                st.success("Application submitted. An administrator will review it.")
                st.rerun()
            except db.StrykeError as ex:
                st.error(str(ex))


def page_coach_dash():
    if not my_coach:
        st.error("No coach profile on this account.")
        return
    c = my_coach
    st.markdown(f"## Coach dashboard · {e(c['name'])}")
    st.markdown(badges(c), unsafe_allow_html=True)
    bs = db.coach_bookings(c["id"])
    done = [b for b in bs if b["status"] == "completed"]
    gross = sum(b["price_cents"] for b in done)
    fees = sum(b["fee_cents"] for b in done)
    m = st.columns(3)
    m[0].metric("Completed sessions", len(done))
    m[1].metric("Gross (completed)", db.money(gross, c["currency"]))
    m[2].metric(f"Your earnings after {db.COMMISSION_PCT:g}% fee", db.money(gross - fees, c["currency"]))
    st.caption("Figures come from persisted bookings. Payouts are not wired yet (no payment provider connected).")
    st.markdown("### Sessions")
    for b in bs:
        with st.container(border=True):
            st.markdown(f"{fmt_slot(db._p(b['start_utc']), c['tz'])} · {e(b['customer_name'])} · **{b['status']}**")
            if b["status"] == "confirmed" and db._p(b["start_utc"]) <= datetime.now(timezone.utc):
                if st.button("Mark completed", key=f"mc{b['id']}"):
                    try:
                        db.complete_booking(user["id"], b["id"])
                        st.rerun()
                    except (db.StrykeError, PermissionError) as ex:
                        st.error(str(ex))
    st.markdown("### Weekly availability")
    st.caption(f"Times in {c['tz']}. Weekday 0 = Monday … 6 = Sunday. Session length is set below.")
    rows = st.data_editor(db.get_availability(c["id"]), num_rows="dynamic", key="avail",
                          column_config={"weekday": st.column_config.NumberColumn("weekday", min_value=0, max_value=6, step=1),
                                         "start_t": "start (HH:MM)", "end_t": "end (HH:MM)"})
    if st.button("Save availability"):
        try:
            db.set_availability(user["id"], rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows))
            st.success("Availability saved.")
        except (db.StrykeError, KeyError, TypeError, ValueError) as ex:
            st.error(str(ex) if isinstance(ex, db.StrykeError) else "Fill in every row completely.")
    st.markdown("### Profile & pricing")
    with st.form("prof"):
        price = st.number_input("Price per session", 0, 5000, c["price_cents"] // 100)
        mins = st.selectbox("Session length (min)", [30, 45, 60, 90, 120], [30, 45, 60, 90, 120].index(c["session_minutes"]))
        bio = st.text_area("Biography", c["bio"])
        style = st.text_input("Coaching style", c["style"])
        if st.form_submit_button("Save profile"):
            try:
                db.update_coach(user["id"], {"price_cents": int(price) * 100, "session_minutes": mins, "bio": bio, "style": style})
                st.success("Saved. (Verification status can only be changed by an administrator.)")
            except db.StrykeError as ex:
                st.error(str(ex))


def page_admin():
    if not db.is_admin(user):  # enforced server-side in every db function too
        st.error("Not authorised.")
        return
    st.markdown("## Admin")
    t = st.tabs(["Applications", "Metrics", "Coaches & users", "Bookings", "Audit log", "Gyms"])
    with t[0]:
        apps = db.list_applications(user)
        if not apps:
            st.info("No applications.")
        for a in apps:
            with st.expander(f"#{a['id']} · {a['data'].get('full_name')} · {a['status']}"):
                st.json(a["data"])
                for fn in a["files"]:
                    st.download_button(f"Download {fn}", db.read_evidence(user, a["id"], fn), file_name=fn, key=f"dl{a['id']}{fn}")
                note = st.text_input("Note to applicant (required for reject / more info)", key=f"n{a['id']}")
                cs = st.columns(4)
                for col, (lbl, stt) in zip(cs, [("Start review", "under_review"), ("Request info", "needs_info"),
                                                ("Approve ✓", "approved"), ("Reject", "rejected")]):
                    if col.button(lbl, key=f"{stt}{a['id']}"):
                        try:
                            db.review_application(user, a["id"], stt, note)
                            st.rerun()
                        except db.StrykeError as ex:
                            st.error(str(ex))
    with t[1]:
        for k, v in db.metrics(user).items():
            st.metric(k, v)
    tb = db.admin_tables(user)
    with t[2]:
        st.dataframe(tb["coaches"])
        cid = st.number_input("Coach id to suspend/unsuspend", 1, 100000, 1)
        c1, c2 = st.columns(2)
        if c1.button("Suspend coach"):
            db.set_suspended(user, "coach", int(cid), True)
            st.rerun()
        if c2.button("Unsuspend coach"):
            db.set_suspended(user, "coach", int(cid), False)
            st.rerun()
        st.dataframe(tb["users"])
    with t[3]:
        st.dataframe(tb["bookings"])
    with t[4]:
        st.dataframe(tb["audit"])
    with t[5]:
        st.markdown("#### Pending ownership claims")
        claims = db.list_claims(user)
        if not claims:
            st.info("No pending claims.")
        for cl in claims:
            with st.container(border=True):
                st.markdown(f"**#{cl['id']} {e(cl['name'])}** · {e(cl['city'] or '')} · claimant: {e(cl['email'])}")
                st.caption(f"Gym website: {cl['website'] or '—'}  |  Claimant says: {cl['claim_note']}")
                g1, g2 = st.columns(2)
                if g1.button("Approve claim", key=f"ca{cl['id']}"):
                    db.review_claim(user, cl["id"], True)
                    st.rerun()
                if g2.button("Reject claim", key=f"cr{cl['id']}"):
                    db.review_claim(user, cl["id"], False)
                    st.rerun()
        st.markdown("#### All gyms")
        st.dataframe(tb["gyms"])
        gid = st.number_input("Gym id", 1, 10000000, 1, key="adm_gid")
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("Verify gym"):
            db.set_gym_verified(user, int(gid), True)
            st.rerun()
        if q2.button("Unverify gym"):
            db.set_gym_verified(user, int(gid), False)
            st.rerun()
        if q3.button("Hide gym"):
            db.set_suspended(user, "gym", int(gid), True)
            st.rerun()
        if q4.button("Unhide gym"):
            db.set_suspended(user, "gym", int(gid), False)
            st.rerun()


# --------------------------------------------------------------- gym map
def logo_img(g, size=48):
    if g.get("logo_b64"):
        return (f'<img src="data:{e(g["logo_mime"])};base64,{g["logo_b64"]}" alt="logo" '
                f'style="width:{size}px;height:{size}px;border-radius:12px;object-fit:cover;float:left;margin-right:.8rem;background:#000">')
    return (f'<div class="avatar" style="width:{size}px;height:{size}px;font-size:{size * 0.4:.0f}px">'
            f'{e(initials(g["name"]) or "?")}</div>')


def pt_label(g):
    if g["pt_status"] == "yes":
        return f"PT from {db.money(g['pt_price_cents'], g['currency'])}" if g.get("pt_price_cents") else "PT offered · ask the gym for price"
    return "No PT" if g["pt_status"] == "no" else "PT: not confirmed"


def gym_badges(g):
    out = []
    if g["pt_status"] == "yes":
        out.append('<span class="badge-ok">PT</span>')
    if g.get("verified"):
        out.append('<span class="badge-ok">✓ VERIFIED GYM</span>')
    if not g.get("owner_id"):
        out.append('<span class="badge-no">From OpenStreetMap · unclaimed</span>')
    return " ".join(out)


def gym_card(g, key):
    dist = f" · {g['distance_km']:.1f} km" if g.get("distance_km") is not None else ""
    chips = "".join(f'<span class="chip">{e(x)}</span>' for x in g["sports"][:4])
    st.markdown(
        f'<div class="card">{logo_img(g)}<h4>{e(g["name"])}</h4>'
        f'<div class="muted">{e(g["city"] or g["address"] or "")}{dist}</div>'
        f'<div style="clear:both;margin:.5rem 0">{gym_badges(g)}</div>{chips}'
        f'<div style="margin-top:.6rem;font-weight:800">{e(pt_label(g))}</div></div>', unsafe_allow_html=True)
    st.button("View gym", key=f"g_{key}_{g['id']}", on_click=nav, args=("gym", None, g["id"]), use_container_width=True)


def _zoom_for(r):
    return 13 if r <= 3 else 12 if r <= 7 else 11 if r <= 15 else 10 if r <= 30 else 9


@st.cache_resource(show_spinner=False, max_entries=6)
def build_map(sig, lat, lon, radius, zoom, _gyms, _coaches):
    """Same inputs -> the very same map object -> the browser keeps the map exactly as the visitor left it."""
    import folium
    from folium.plugins import MarkerCluster
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None, control_scale=True, scrollWheelZoom=True)
    folium.TileLayer(tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", name="Dark",
                     attr="© OpenStreetMap contributors © CARTO", subdomains="abcd", max_zoom=19).add_to(m)
    folium.TileLayer(tiles="OpenStreetMap", name="Street map").add_to(m)
    folium.Circle([lat, lon], radius=radius * 1000, color=ACCENT, weight=1, fill=False, dash_array="6").add_to(m)
    folium.CircleMarker([lat, lon], radius=5, color="#fff", fill=True, fill_color="#fff", tooltip="Search centre").add_to(m)
    cluster = MarkerCluster(name="Gyms").add_to(m)
    for g in _gyms:
        col = ACCENT if g["pt_status"] == "yes" else "#6E6E78"
        site = f'<br><a href="{e(g["website"])}" target="_blank" rel="noopener">Website</a>' if g["website"] else ""
        pop = (f'<div style="font-family:sans-serif;min-width:190px;color:#111;overflow:auto">{logo_img(g, 44)}'
               f'<b>{e(g["name"])}</b><br>{e(pt_label(g))}<br><small>{e(", ".join(g["sports"][:4]))}</small>{site}</div>')
        folium.CircleMarker([g["lat"], g["lon"]], radius=10 if g["pt_status"] == "yes" else 7, color="#000", weight=1, fill=True,
                            fill_color=col, fill_opacity=.95, tooltip=g["name"],
                            popup=folium.Popup(pop, max_width=280)).add_to(cluster)
    for c in _coaches:
        pop = (f'<div style="font-family:sans-serif;color:#111"><b>{e(c["name"])}</b><br>Coach · '
               f'{e(db.money(c["price_cents"], c["currency"]))} / {c["session_minutes"]} min<br><small>{e(", ".join(c["sports"]))}</small></div>')
        folium.CircleMarker([c["lat"], c["lon"]], radius=8, color="#fff", weight=2, fill=True, fill_color="#FF2E63", fill_opacity=.95,
                            tooltip=f"Coach: {c['name']}", popup=folium.Popup(pop, max_width=260)).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def page_gyms():
    try:
        import folium  # noqa: F401
        from streamlit_folium import st_folium
    except ImportError:
        st.error("Map components are missing. Make sure requirements.txt contains folium and streamlit-folium.")
        return

    st.markdown("## Gym map")
    st.caption("Drag to move, scroll or pinch to zoom, click a dot for details. Gyms are loaded from OpenStreetMap for the area you look "
               "at, so search any place in the world. Logo, PT and price only appear when the gym itself has added them.")

    def recenter(la, lo, label):
        ss.map_center, ss.map_label, ss.last_fetch = (la, lo), label, None
        ss.view_center, ss.view_zoom = None, None

    # ---- where to look
    with st.form("placeform", border=False):
        pc = st.columns([3, 1])
        place = pc[0].text_input("Search any place in the world", placeholder="Bangkok · Rio de Janeiro · Karl Johans gate, Oslo",
                                 label_visibility="collapsed")
        go = pc[1].form_submit_button("🔍 Search", type="primary", use_container_width=True)
    lc = st.columns([1.3, 1.5, 2])
    if lc[0].button("📍 Use my location (GPS)"):
        ss.gps_map = True
    if ss.gps_map:
        try:
            from streamlit_js_eval import get_geolocation
            g = get_geolocation()
            if g and "coords" in g:
                recenter(g["coords"]["latitude"], g["coords"]["longitude"], "your GPS position")
                ss.gps_map = False
                st.rerun()
            elif g and "error" in g:
                st.warning("Location permission denied or unavailable. Search a place instead.")
                ss.gps_map = False
            else:
                st.info("Waiting for browser location permission…")
        except Exception:
            st.warning("GPS component unavailable. Search a place instead.")
            ss.gps_map = False
    quick = lc[1].selectbox("Quick jump", ["—"] + list(db.CITIES), label_visibility="collapsed")
    if quick != "—" and quick != ss.get("_quick_prev"):
        ss._quick_prev = quick
        recenter(*db.CITIES[quick][:2], quick)
    if go and place.strip():
        try:
            hit = db.geocode(place.strip())
            if hit:
                recenter(hit["lat"], hit["lon"], hit["label"])
            else:
                st.warning("Could not find that place. Try a bigger city or add the country.")
        except db.StrykeError as ex:
            st.warning(str(ex))
    lc[2].caption(f"Centered on: {ss.map_label}")

    # ---- filters
    f = st.columns([1.2, 1.5, 1.2, 1, 1])
    radius = f[0].slider("Radius (km)", 2, 50, 15)
    sports = f[1].multiselect("Martial art", db.GYM_SPORTS)
    qtxt = f[2].text_input("Name filter", placeholder="gym name…")
    pt_only = f[3].checkbox("Only gyms with PT", value=False)
    show_coaches = f[4].checkbox("Show coaches", value=True)

    lat, lon = ss.map_center
    key = (round(lat, 2), round(lon, 2), radius)
    if ss.last_fetch != key:
        ss.last_fetch = key
        try:
            with st.spinner("Loading gyms from OpenStreetMap…"):
                db.fetch_osm(lat, lon, radius)
        except db.StrykeError as ex:
            st.warning(str(ex))
    rb = st.columns([1.4, 1.6, 3])
    if rb[0].button("🔄 Reload this area"):
        try:
            with st.spinner("Reloading…"):
                db.fetch_osm(lat, lon, radius, force=True)
        except db.StrykeError as ex:
            st.warning(str(ex))

    gyms = db.gyms_near(lat, lon, radius, sports, pt_only, qtxt)
    coaches = []
    if show_coaches:
        coaches = [c for c in db.search_coaches(sports=[x for x in sports if x in db.SPORTS] or None)
                   if db.haversine_km(lat, lon, c["lat"], c["lon"]) <= radius]

    # ---- map (built once per area/filters and cached, so reruns never re-render or reset it)
    sig = hashlib.md5(repr((
        [(g["id"], g["name"], g["pt_status"], g["pt_price_cents"], g["currency"], len(g["logo_b64"] or ""), g["website"]) for g in gyms[:600]],
        [(c["id"], c["price_cents"]) for c in coaches])).encode()).hexdigest()
    m = build_map(sig, round(lat, 5), round(lon, 5), radius, _zoom_for(radius), gyms[:600], coaches)

    opts = dict(key="gymmap", height=560, returned_objects=["last_object_clicked"])
    try:
        ret = st_folium(m, use_container_width=True, **opts)
    except TypeError:
        ret = st_folium(m, width=1100, **opts)
    st.markdown(f'<span class="chip acc">● PT confirmed</span><span class="chip">● PT not confirmed</span>'
                f'<span class="chip" style="border-color:#FF2E63;color:#FF2E63">● Coach</span>'
                f'<span class="muted"> {len(gyms)} gyms · {len(coaches)} coaches within {radius} km</span>', unsafe_allow_html=True)

    if ret:
        lc_ = ret.get("last_object_clicked")
        if lc_:
            best, bd = None, 0.08
            for kind, items in (("gym", gyms), ("coach", coaches)):
                for it in items:
                    d = db.haversine_km(lc_["lat"], lc_["lng"], it["lat"], it["lng"])
                    if d < bd:
                        best, bd = (kind, it["id"]), d
            if best:
                ss.sel = best

    sel = ss.sel
    if sel and sel[0] == "gym":
        g = db.get_gym(sel[1])
        if g:
            st.markdown("### Selected")
            gym_card(g, "sel")
    elif sel and sel[0] == "coach":
        c = db.get_coach(sel[1])
        if c:
            st.markdown("### Selected")
            coach_card(c, "sel")

    st.markdown("### Gyms in this area")
    if not gyms:
        st.info("No gyms found here yet. Try a larger radius, another place, or add your own gym with “List your gym”.")
    shown = gyms[:60]
    for i in range(0, len(shown), 3):
        for col, g in zip(st.columns(3), shown[i:i + 3]):
            with col:
                gym_card(g, f"l{i}")
    if len(gyms) > len(shown):
        st.caption(f"Showing the nearest {len(shown)} of {len(gyms)}. Narrow the filters to see others.")


def page_gym():
    g = db.get_gym(ss.gym_id)
    if not g or g["suspended"]:
        st.error("Gym not found.")
        return
    st.button("← Back to map", on_click=nav, args=("gyms",))
    st.markdown(f'{logo_img(g, 84)}<h1 style="margin:0">{e(g["name"])}</h1>'
                f'<div class="muted">{e(g["address"] or "")} {e(g["city"] or "")} {e(g["country"] or "")}</div>'
                f'<div style="clear:both;margin:.5rem 0 1rem">{gym_badges(g)}</div>', unsafe_allow_html=True)
    left, right = st.columns([2, 1.2])
    with left:
        st.markdown("".join(f'<span class="chip acc">{e(x)}</span>' for x in g["sports"]), unsafe_allow_html=True)
        st.write(g["description"] or "No description yet.")
        st.markdown("### Contact")
        if g["phone"]:
            st.markdown(f"**Phone:** {e(g['phone'])}")
        if g["email"]:
            st.markdown(f"**Email:** {e(g['email'])}")
        if not (g["phone"] or g["email"] or g["website"]):
            st.caption("No contact details listed yet.")
        b = st.columns(2)
        if g["website"]:
            b[0].link_button("Website", g["website"], use_container_width=True)
        b[1].link_button("Directions", f"https://www.google.com/maps/dir/?api=1&destination={g['lat']},{g['lon']}", use_container_width=True)
        import pandas as pd
        st.map(pd.DataFrame({"lat": [g["lat"]], "lon": [g["lon"]]}), zoom=14)
    with right:
        price = (f'<div class="num">{db.money(g["pt_price_cents"], g["currency"])}</div><div class="muted">per personal-training session</div>'
                 if g["pt_status"] == "yes" and g.get("pt_price_cents") else
                 f'<div class="num" style="font-size:1.4rem">{e(pt_label(g))}</div>')
        st.markdown(f'<div class="card">{price}</div>', unsafe_allow_html=True)
        if not g["owner_id"]:
            st.markdown('<div class="banner">This listing comes from OpenStreetMap. The gym has not added its own logo, PT status or prices yet.</div>',
                        unsafe_allow_html=True)
        if user and g["owner_id"] == user["id"]:
            st.success("You manage this gym.")
            st.button("Edit gym", on_click=nav, args=("gym_manage",), type="primary", use_container_width=True)
        elif not g["owner_id"]:
            st.markdown("#### Is this your gym?")
            if g["claim_status"] == "pending":
                st.info("A claim is waiting for admin review.")
            elif not user:
                st.button("Log in to claim", on_click=nav, args=("account",), key="clg")
            else:
                note = st.text_area("How are you connected to this gym? (role, website, work email)", max_chars=500, key="claimnote")
                if st.button("Claim this gym", type="primary", use_container_width=True):
                    try:
                        db.claim_gym(user["id"], g["id"], note)
                        st.success("Claim sent. An administrator will review it.")
                        st.rerun()
                    except db.StrykeError as ex:
                        st.error(str(ex))


def gym_form(g, key):
    d = g or {}
    with st.form(key):
        name = st.text_input("Gym / club name", d.get("name", ""))
        c1, c2 = st.columns(2)
        address = c1.text_input("Street address", d.get("address", ""))
        city = c2.text_input("City", d.get("city", ""))
        c3, c4, c5 = st.columns(3)
        website = c3.text_input("Website", d.get("website", ""))
        phone = c4.text_input("Phone", d.get("phone", ""))
        email = c5.text_input("Contact email (shown publicly)", d.get("email", ""))
        sports = st.multiselect("Martial arts offered", db.GYM_SPORTS, d.get("sports", []))
        desc = st.text_area("About the gym", d.get("description", ""), max_chars=1000)
        pts = ["yes", "no", "unknown"]
        pt = st.radio("Do you offer personal training (PT) in martial arts?", pts, index=pts.index(d.get("pt_status", "unknown")),
                      format_func={"yes": "Yes, PT offered", "no": "No", "unknown": "Not sure / not shown"}.get, horizontal=True)
        p1, p2 = st.columns(2)
        price = p1.number_input("PT price per session (0 = ask the gym)", 0, 100000, int((d.get("pt_price_cents") or 0) // 100))
        cur = d.get("currency") or "NOK"
        curr = p2.selectbox("Currency", db.CURRENCIES, db.CURRENCIES.index(cur) if cur in db.CURRENCIES else 0)
        logo = st.file_uploader("Club logo (PNG / JPG / WEBP)", type=["png", "jpg", "jpeg", "webp"])
        rm = st.checkbox("Remove current logo") if d.get("logo_b64") else False
        if st.form_submit_button("Save gym" if g else "Add gym", type="primary"):
            data = dict(name=name, address=address, city=city, website=website, phone=phone, email=email, sports=sports,
                        description=desc, pt_status=pt, price=price, currency=curr)
            blob = (logo.name, logo.getvalue()) if logo else None
            try:
                if g:
                    db.update_gym(user["id"], g["id"], data, blob, rm)
                    st.success("Saved.")
                else:
                    gid = db.create_gym(user["id"], data, blob)
                    st.success("Gym added to the map.")
                    ss.gym_id = gid
            except (db.StrykeError, PermissionError) as ex:
                st.error(str(ex))


def page_gym_manage():
    st.markdown("## List your gym")
    st.caption("Add your gym to the map with logo, martial arts and PT price. Listings are shown publicly. A ✓ verified badge is only given by a STRYKE administrator.")
    if not user:
        st.info("Log in or create an account first.")
        st.button("Log in / Sign up", on_click=nav, args=("account",), key="gm1")
        return
    mine = db.user_gyms(user["id"])
    t1, t2 = st.tabs(["My gyms", "Add a new gym"])
    with t1:
        owned = [g for g in mine if g["owner_id"] == user["id"]]
        pend = [g for g in mine if g["owner_id"] != user["id"]]
        for g in pend:
            st.info(f"Claim for “{g['name']}” is waiting for admin review.")
        if not owned:
            st.caption("You have no gyms yet. Add one, or open a gym on the map and press “Claim this gym”.")
        else:
            sel = st.selectbox("Choose gym", [g["id"] for g in owned], format_func=lambda i: next(x["name"] for x in owned if x["id"] == i))
            g = db.get_gym(sel)
            st.button("View public page", on_click=nav, args=("gym", None, sel), key="gm2")
            gym_form(g, f"edit{sel}")
    with t2:
        gym_form(None, "newgym")


def page_legal():
    st.markdown("## Privacy & Terms (DRAFT)")
    st.markdown('<div class="banner">Placeholder drafts. Must be reviewed and completed by a qualified lawyer before launch.</div>', unsafe_allow_html=True)
    st.markdown("**Privacy (draft).** STRYKE stores account details, bookings and coach applications. Coach evidence is private and visible only to administrators. "
                "Location is used only after you grant browser permission and is not stored.")
    st.markdown("**Terms (draft).** STRYKE is a marketplace connecting customers and independent coaches. Training carries injury risk. "
                "Cancellation: free up to the configured window; later cancellations are not refunded.")


header()
{"home": page_home, "coaches": page_coaches, "profile": page_profile, "account": page_account, "dashboard": page_dashboard,
 "apply": page_apply, "coach_dash": page_coach_dash, "admin": page_admin, "legal": page_legal,
 "gyms": page_gyms, "gym": page_gym, "gym_manage": page_gym_manage}.get(ss.page, page_home)()
st.divider()
fc = st.columns([1, 1, 4])
fc[0].button("Privacy & Terms", on_click=nav, args=("legal",), key="legal")
fc[2].caption("STRYKE · Find your coach. Train like a fighter.")
