"""STRYKE - Find your coach. Train like a fighter. (Streamlit app)"""
import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import streamlit as st
import db

ACCENT = "#00D1FF"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;900&display=swap');
:root {{ --acc:{ACCENT}; --bg:#0A0A0B; --card:#141416; --line:#26262A; --mut:#9A9AA3; }}
html, body, [class*="css"] {{ font-family:'Inter',sans-serif; }}
.stApp {{ background:var(--bg); }}
.block-container {{ padding-top:1.2rem; max-width:1180px; }}
.brand {{ font-weight:900; font-size:1.7rem; letter-spacing:.12em; color:#fff; }}
.brand b {{ color:var(--acc); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:1.2rem 1.3rem; height:100%; }}
.chip {{ display:inline-block; padding:.35rem .8rem; margin:.2rem .25rem .2rem 0; border:1px solid var(--line); border-radius:999px; color:#ddd; font-size:.85rem; background:#101012; }}
.chip.acc {{ border-color:var(--acc); color:var(--acc); }}
.muted {{ color:var(--mut); font-size:.9rem; }}
.num {{ font-weight:900; font-size:2rem; color:var(--acc); }}
.avatar {{ width:56px; height:56px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-weight:900; font-size:1.3rem; color:#000; background:var(--acc); float:left; margin-right:.9rem; }}
.badge-ok {{ color:#000; background:var(--acc); padding:.15rem .55rem; border-radius:6px; font-size:.75rem; font-weight:800; }}
.badge-no {{ color:var(--mut); border:1px solid var(--line); padding:.1rem .5rem; border-radius:6px; font-size:.72rem; }}
.banner {{ border:1px dashed #FFB020; color:#FFB020; border-radius:12px; padding:.7rem 1rem; font-size:.9rem; margin:.6rem 0; }}
.stButton>button {{ border-radius:12px; font-weight:700; border:1px solid var(--line); background:#141416; color:#F5F5F7; }}
.stButton>button[kind="primary"] {{ background:var(--acc); color:#000; border:none; }}
</style>
"""

st.set_page_config(page_title="STRYKE", page_icon="🥊", layout="wide")
db.init()
st.markdown(CSS, unsafe_allow_html=True)

ss = st.session_state
for k, v in {"page": "home", "uid": None, "coach_id": None, "origin": None, "gps_ask": False, "gym_id": None,
             "map_center": (59.9139, 10.7522), "map_label": "Oslo", "last_fetch": None, "sel": None, "gps_map": False}.items():
    ss.setdefault(k, v)

user = db.get_user(ss.uid)
e = html.escape


def nav(page, coach_id=None, gym_id=None):
    ss.page = page
    if coach_id is not None:
        ss.coach_id = coach_id
    if gym_id is not None:
        ss.gym_id = gym_id


def initials(name):
    n = name.replace("Demo:", "").split()
    return "".join(p[0] for p in n[:2]).upper()


def pt_label(g):
    if g["pt_status"] == "yes":
        return f"PT fra {db.money(g['pt_price_cents'], g['currency'])}" if g.get("pt_price_cents") else "PT tilbys"
    return "Ingen PT" if g["pt_status"] == "no" else "PT: uavklart"


def logo_img(g, size=48):
    if g.get("logo_b64"):
        return f'<img src="data:{e(g["logo_mime"])};base64,{g["logo_b64"]}" style="width:{size}px;height:{size}px;border-radius:12px;object-fit:cover;float:left;margin-right:.8rem;background:#000">'
    return f'<div class="avatar" style="width:{size}px;height:{size}px;font-size:{size * 0.4:.0f}px">{e(initials(g["name"]) or "?")}</div>'


def header():
    cols = st.columns([1.8, 1, 1, 1.1, 1, 1.4])
    cols[0].markdown('<div class="brand">STRY<b>K</b>E</div>', unsafe_allow_html=True)
    cols[1].button("Finn trener", on_click=nav, args=("coaches",), use_container_width=True)
    cols[2].button("🗺️ Gym-kart", on_click=nav, args=("gyms",), use_container_width=True, key="hg")
    cols[3].button("Registrer gym", on_click=nav, args=("gym_manage",), use_container_width=True)
    if user:
        cols[4].button("Mine bookinger", on_click=nav, args=("dashboard",), use_container_width=True)
        cols[5].button(f"Konto · {user['name'].split()[0]}", on_click=nav, args=("account",), use_container_width=True)
    else:
        cols[4].write("")
        cols[5].button("Logg inn / Registrer", on_click=nav, args=("account",), type="primary", use_container_width=True)


def gym_card(g, key):
    dist = f" · {g['distance_km']:.1f} km" if g.get("distance_km") is not None else ""
    chips = "".join(f'<span class="chip">{e(x)}</span>' for x in g["sports"][:4])
    st.markdown(
        f'<div class="card">{logo_img(g)}<h4>{e(g["name"])}</h4>'
        f'<div class="muted">{e(g["city"] or g["address"] or "")}{dist}</div>'
        f'<div style="clear:both;margin:.5rem 0"><span class="badge-ok">PT</span></div>{chips}'
        f'<div style="margin-top:.6rem;font-weight:800">{e(pt_label(g))}</div></div>', unsafe_allow_html=True)
    st.button("Vis gym", key=f"g_{key}_{g['id']}", on_click=nav, args=("gym", None, g["id"]), use_container_width=True)


def _zoom_for(r):
    return 13 if r <= 3 else 12 if r <= 7 else 11 if r <= 15 else 10 if r <= 30 else 9


# ------------------------------------------------------------------ Sider
def page_home():
    st.markdown(
        '<div style="padding:3rem 2rem;border:1px solid #26262A;border-radius:24px;background:#0E0E10;">'
        '<h1 style="font-size:3rem;color:#fff;">Finn kampsport-gymmer & PT i hele verden.<br><em>Norge, Thailand, USA & mer.</em></h1>'
        '<p style="color:#9A9AA3;font-size:1.15rem;">Søk gjennom tusenvis av gymmer, sjekk priser, se logoer og finn personlige trenere.</p></div>',
        unsafe_allow_html=True)
    st.markdown("### Utforsk på kartet")
    if st.button("🗺️ Åpne verdenskartet nå", type="primary", use_container_width=True):
        nav("gyms")
        st.rerun()


def page_gyms():
    import pandas as pd
    import pydeck as pdk

    st.markdown("## 🗺️ Gym-kart (Globalt)")
    st.caption("Søk i hele verden (Norge, USA, Thailand, osv.). Klikk på et punkt for detaljer.")

    world = st.radio("Visning", ["📍 Nær et sted", "🌍 Hele verden"], horizontal=True, label_visibility="collapsed", key="map_mode").startswith("🌍")

    def recenter(la, lo, label):
        ss.map_center, ss.map_label, ss.last_fetch = (la, lo), label, None

    lat, lon = ss.map_center
    if not world:
        with st.form("placeform", border=False):
            pc = st.columns([3, 1])
            place = pc[0].text_input("Søk på sted (f.eks. Bangkok, Oslo, New York, Phuket)", label_visibility="collapsed")
            go = pc[1].form_submit_button("🔍 Søk", type="primary", use_container_width=True)

        quick = st.selectbox("Hurtighopp til byer", ["—"] + list(db.CITIES))
        if quick != "—":
            recenter(*db.CITIES[quick][:2], quick)

        if go and place.strip():
            hit = db.geocode(place.strip())
            if hit:
                recenter(hit["lat"], hit["lon"], hit["label"])
            else:
                st.warning("Fant ikke stedet.")
        lat, lon = ss.map_center
    else:
        st.info("Viser alle lagrede gymmer globalt.")

    f = st.columns([1.2, 1.6, 1.3, 1])
    radius = f[0].slider("Radius (km)", 2, 100, 25, disabled=world)
    sports = f[1].multiselect("Kampsport", db.GYM_SPORTS)
    qtxt = f[2].text_input("Navnefilter", placeholder="gymnavn…")
    pt_only = f[3].checkbox("Kun gym med PT", value=False)

    if world:
        gyms = db.gyms_all(sports, pt_only, qtxt)
    else:
        key = (round(lat, 2), round(lon, 2), radius)
        if ss.last_fetch != key:
            ss.last_fetch = key
            try:
                db.fetch_osm(lat, lon, radius)
            except Exception:
                pass
        gyms = db.gyms_near(lat, lon, radius, sports, pt_only, qtxt)

    g_list = []
    for g in gyms:
        g_list.append({
            "id": g["id"], "name": str(g["name"]), "lat": float(g["lat"]), "lon": float(g["lon"]),
            "pt": pt_label(g), "sports": ", ".join(g["sports"][:3]) if isinstance(g["sports"], list) else "",
            "r": 0 if g["pt_status"] == "yes" else 120, "g": 209 if g["pt_status"] == "yes" else 120,
            "b": 255 if g["pt_status"] == "yes" else 130, "a": 220,
            "radius": 12 if g["pt_status"] == "yes" else 8
        })

    df_gyms = pd.DataFrame(g_list)
    zoom_lvl = 1.8 if world else (_zoom_for(radius) - 1)
    view_state = pdk.ViewState(latitude=float(lat) if not world else 20.0, longitude=float(lon) if not world else 0.0, zoom=zoom_lvl, pitch=0)

    layers = []
    if not df_gyms.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_gyms,
                get_position=["lon", "lat"],
                get_fill_color="[r, g, b, a]",
                get_radius="radius",
                radius_units="pixels",
                radius_min_pixels=5,
                radius_max_pixels=18,
                stroked=True,
                get_line_color=[0, 0, 0, 255],
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
            )
        )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={"html": "<b>{name}</b><br/>{pt}<br/><i>{sports}</i>", "style": {"backgroundColor": "#141416", "color": "#F5F5F7"}}
    )

    try:
        event = st.pydeck_chart(deck, height=520, on_select="rerun", selection_mode="single-object", key="gym_deck")
        if event and hasattr(event, "selection") and event.selection:
            objs = event.selection.get("objects", {})
            for lst in objs.values():
                if lst:
                    ss.sel = ("gym", lst[0]["id"])
                    break
    except Exception:
        st.pydeck_chart(deck, height=520)

    sel = ss.get("sel")
    if sel and sel[0] == "gym":
        g = db.get_gym(sel[1])
        if g:
            st.markdown("### Valgt gym")
            gym_card(g, "sel")

    st.markdown(f"### Gymmer i området ({len(gyms)})")
    shown = gyms[:60]
    for i in range(0, len(shown), 3):
        cols = st.columns(3)
        for col, g in zip(cols, shown[i:i + 3]):
            with col:
                gym_card(g, f"grid_{i}_{g['id']}")


def page_gym():
    g = db.get_gym(ss.gym_id)
    if not g:
        st.error("Gym ikke funnet.")
        return
    st.button("← Tilbake til kart", on_click=nav, args=("gyms",))
    st.markdown(f'{logo_img(g, 84)}<h1 style="margin:0">{e(g["name"])}</h1>'
                f'<div class="muted">{e(g["address"] or "")} {e(g["city"] or "")} {e(g["country"] or "")}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("".join(f'<span class="chip acc">{e(x)}</span>' for x in g["sports"]), unsafe_allow_html=True)
    st.write(g["description"] or "Ingen beskrivelse.")
    if g["website"]:
        st.link_button("Besøk nettside", g["website"])


def page_gym_manage():
    st.markdown("## Registrer / Administrer ditt Gym")
    if not user:
        st.info("Logg inn for å registrere et gym.")
        return
    mine = db.user_gyms(user["id"])
    t1, t2 = st.tabs(["Mine gymmer", "Legg til nytt gym"])
    with t1:
        for g in mine:
            st.markdown(f"**{g['name']}** ({g['city']})")
    with t2:
        with st.form("newgym"):
            name = st.text_input("Gymnavn")
            address = st.text_input("Gateadresse")
            city = st.text_input("By")
            sports = st.multiselect("Kampsport", db.GYM_SPORTS)
            desc = st.text_area("Beskrivelse")
            pt = st.radio("Tilbyr PT?", ["yes", "no", "unknown"])
            price = st.number_input("PT-pris per sesjon", 0, 10000, 500)
            cur = st.selectbox("Valuta", db.CURRENCIES)
            logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
            if st.form_submit_button("Lagre gym", type="primary"):
                try:
                    blob = (logo.name, logo.getvalue()) if logo else None
                    db.create_gym(user["id"], dict(name=name, address=address, city=city, sports=sports, description=desc,
                                                   pt_status=pt, price=price, currency=cur), blob)
                    st.success("Gym lagt til på kartet!")
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))


def page_account():
    if user:
        st.markdown(f"## Konto: {user['name']}")
        if st.button("Logg ut"):
            ss.uid = None
            st.rerun()
        return
    t1, t2 = st.tabs(["Logg inn", "Registrer"])
    with t1:
        with st.form("login"):
            em = st.text_input("E-post")
            pw = st.text_input("Passord", type="password")
            if st.form_submit_button("Logg inn"):
                try:
                    ss.uid = db.login(em, pw)
                    st.rerun()
                except db.StrykeError as ex:
                    st.error(str(ex))
    with t2:
        with st.form("signup"):
            nm = st.text_input("Navn")
            em = st.text_input("E-post")
            pw = st.text_input("Passord (min 8 tegn)", type="password")
            if st.form_submit_button("Registrer"):
                try:
                    ss.uid = db.register(em, nm, pw)
                    st.rerun()
                except db.StrykeError as ex:
                    st.error(str(ex))


def page_dashboard():
    st.markdown("## Mine bookinger")
    if not user:
        st.info("Logg inn.")
        return
    bs = db.user_bookings(user["id"])
    for b in bs:
        st.markdown(f"**{b['coach_name']}** · {b['status']} · {db.money(b['price_cents'], b['currency'])}")


def page_coaches():
    st.markdown("## Finn personlig trener (Coach)")
    res = db.search_coaches()
    for c in res:
        with st.container(border=True):
            st.markdown(f"### {c['name']} ({c['city']})")
            st.write(f"Pris: {db.money(c['price_cents'], c['currency'])} / {c['session_minutes']} min")
            if st.button("Bestill / Vis", key=f"c_{c['id']}"):
                nav("profile", coach_id=c['id'])
                st.rerun()


def page_profile():
    c = db.get_coach(ss.coach_id)
    if not c:
        return
    st.button("← Tilbake", on_click=nav, args=("coaches",))
    st.markdown(f"# {c['name']}")
    st.write(f"By: {c['city']}")
    st.markdown(f"### Pris: {db.money(c['price_cents'], c['currency'])}")
    slots = db.free_slots(c['id'])
    if slots:
        pick = st.selectbox("Velg tidspunkt", slots, format_func=lambda s: s.strftime("%a %d %b, %H:%M"))
        if st.button("Bekreft booking (Testmodus)", type="primary"):
            db.create_booking(user["id"], c['id'], pick)
            st.success("Booking fullført!")


header()
PAGES = {"home": page_home, "gyms": page_gyms, "gym": page_gym, "gym_manage": page_gym_manage,
         "account": page_account, "dashboard": page_dashboard, "coaches": page_coaches, "profile": page_profile}
try:
    PAGES.get(ss.page, page_home)()
except Exception as ex:
    st.error("Noe gikk galt.")
    st.exception(ex)
