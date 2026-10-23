"""STRYKE - Find your coach. Train like a fighter.  (Streamlit app)"""
import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

import db.py
import theme

st.set_page_config(page_title="STRYKE", page_icon="🥊", layout="wide")
db.init()
st.markdown(theme.CSS, unsafe_allow_html=True)
ss = st.session_state
for k, v in {"page": "home", "uid": None, "coach_id": None, "origin": None, "gps_ask": False}.items():
    ss.setdefault(k, v)

user = db.get_user(ss.uid)  # re-read every run so suspensions apply immediately
if ss.uid and not user:
    ss.uid = None
my_coach = db.coach_for_user(user["id"]) if user else None
e = html.escape


def nav(page, coach_id=None):
    ss.page = page
    if coach_id is not None:
        ss.coach_id = coach_id


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
    cols = st.columns([2.2, 1, 1, 1, 1.2])
    cols[0].markdown('<div class="brand">STRY<b>K</b>E</div>', unsafe_allow_html=True)
    cols[1].button("Find a coach", on_click=nav, args=("coaches",), use_container_width=True)
    cols[2].button("Become a coach", on_click=nav, args=("apply",), use_container_width=True)
    if user:
        cols[3].button("My bookings", on_click=nav, args=("dashboard",), use_container_width=True)
        lbl = user["name"].split()[0]
        cols[4].button(f"Account · {lbl}", on_click=nav, args=("account",), use_container_width=True)
    else:
        cols[3].write("")
        cols[4].button("Log in / Sign up", on_click=nav, args=("account",), type="primary", use_container_width=True)
    extra = []
    if my_coach:
        extra.append(("Coach dashboard", "coach_dash"))
    if db.is_admin(user):
        extra.append(("Admin", "admin"))
    if extra:
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
    a, b, _ = st.columns([1, 1, 3])
    a.button("Find a coach", type="primary", on_click=nav, args=("coaches",), use_container_width=True, key="h1")
    b.button("Become a coach", on_click=nav, args=("apply",), use_container_width=True, key="h2")

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
    st.caption(f"{len(res)} coach{'es' if len(res) != 1 else ''} found · list view (map needs a map provider, see README)")
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
    t = st.tabs(["Applications", "Metrics", "Coaches & users", "Bookings", "Audit log"])
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


def page_legal():
    st.markdown("## Privacy & Terms (DRAFT)")
    st.markdown('<div class="banner">Placeholder drafts. Must be reviewed and completed by a qualified lawyer before launch.</div>', unsafe_allow_html=True)
    st.markdown("**Privacy (draft).** STRYKE stores account details, bookings and coach applications. Coach evidence is private and visible only to administrators. "
                "Location is used only after you grant browser permission and is not stored.")
    st.markdown("**Terms (draft).** STRYKE is a marketplace connecting customers and independent coaches. Training carries injury risk. "
                "Cancellation: free up to the configured window; later cancellations are not refunded.")


header()
{"home": page_home, "coaches": page_coaches, "profile": page_profile, "account": page_account, "dashboard": page_dashboard,
 "apply": page_apply, "coach_dash": page_coach_dash, "admin": page_admin, "legal": page_legal}.get(ss.page, page_home)()
st.divider()
fc = st.columns([1, 1, 4])
fc[0].button("Privacy & Terms", on_click=nav, args=("legal",), key="legal")
fc[2].caption("STRYKE · Find your coach. Train like a fighter.")

