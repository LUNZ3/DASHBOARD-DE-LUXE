"""CORNERSTONE COMBAT CLUB - find a fight gym with personal training, anywhere on earth.

Run:  pip install -r requirements.txt  &&  streamlit run app.py
"""
import html
import uuid

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen, LocateControl, MarkerCluster
from streamlit_folium import st_folium

import db

try:
    from streamlit_js_eval import get_geolocation
except Exception:  # optional
    get_geolocation = None

st.set_page_config(page_title="Cornerstone Combat Club - Fight gyms worldwide", page_icon="🥊", layout="wide")
db.init()

# ------------------------------------------------------------------ theme: blood red + bone on black
RED, BONE, GOLD = "#E10600", "#F2EDE4", "#C9A227"
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;600;800&display=swap');
:root {{ --red:{RED}; --bone:{BONE}; --gold:{GOLD}; --bg:#0B0A0A; --card:#151313; --line:#2A2525; --mut:#A39C94; }}
html, body, .stApp, [class*="css"] {{ font-family:'Archivo',sans-serif; }}
.stApp {{ background:var(--bg); color:var(--bone); }}
#MainMenu, footer, header[data-testid="stHeader"] {{ visibility:hidden; height:0; }}
.block-container {{ padding-top:1rem; max-width:1300px; }}
h1,h2,h3 {{ font-family:'Anton',sans-serif !important; letter-spacing:.02em; text-transform:uppercase; color:var(--bone) !important; }}
.brand {{ font-family:'Anton'; font-size:1.9rem; letter-spacing:.06em; color:var(--bone); line-height:1; }}
.brand span {{ color:var(--red); }}
.tag {{ color:var(--mut); font-size:.8rem; letter-spacing:.25em; text-transform:uppercase; }}
.hero {{ border:1px solid var(--line); border-radius:4px; padding:3rem 2.2rem; margin:.6rem 0 1.2rem;
  background: linear-gradient(115deg, rgba(225,6,0,.28), transparent 45%),
              repeating-linear-gradient(-45deg, #120f0f 0 14px, #0e0c0c 14px 28px); position:relative; overflow:hidden; }}
.hero h1 {{ font-size:clamp(2.6rem,7vw,5.4rem) !important; line-height:.92; margin:0; }}
.hero h1 em {{ font-style:normal; color:var(--red); }}
.hero p {{ color:var(--mut); max-width:560px; font-size:1.1rem; margin-top:1rem; }}
.stat {{ border-left:3px solid var(--red); padding:.2rem 0 .2rem .9rem; }}
.stat b {{ font-family:'Anton'; font-size:2.2rem; color:var(--bone); display:block; line-height:1; }}
.stat small {{ color:var(--mut); text-transform:uppercase; letter-spacing:.15em; font-size:.7rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:4px; padding:1rem 1.1rem; margin-bottom:.8rem; transition:.15s; }}
.card:hover {{ border-color:var(--red); transform:translateY(-2px); }}
.card h4 {{ margin:0; font-size:1.05rem; color:var(--bone); }}
.card img {{ width:44px; height:44px; border-radius:6px; background:#fff; object-fit:contain; float:left; margin-right:.8rem; }}
.mut {{ color:var(--mut); font-size:.85rem; }}
.chip {{ display:inline-block; padding:.12rem .55rem; margin:.15rem .2rem 0 0; border:1px solid var(--line); font-size:.72rem;
  text-transform:uppercase; letter-spacing:.06em; color:var(--bone); }}
.pt-yes {{ background:var(--red); color:#fff; padding:.12rem .5rem; font-size:.7rem; font-weight:800; letter-spacing:.08em; }}
.pt-unk {{ border:1px dashed var(--mut); color:var(--mut); padding:.1rem .5rem; font-size:.7rem; }}
.star {{ color:var(--gold); }}
.stButton>button, .stLinkButton>a {{ border-radius:2px !important; font-weight:800; text-transform:uppercase; letter-spacing:.06em; }}
.stButton>button[kind="primary"] {{ background:var(--red); border:none; color:#fff; }}
section[data-testid="stSidebar"] {{ background:#0F0D0D; border-right:1px solid var(--line); }}
.stApp p, .stApp label, .stApp li, .stMarkdown {{ color:var(--bone); }}
</style>
""", unsafe_allow_html=True)

if "device" not in st.session_state:
    st.session_state.device = st.query_params.get("d") or uuid.uuid4().hex[:12]
    st.query_params["d"] = st.session_state.device
DEVICE = st.session_state.device
esc = html.escape


def pt_badge(g):
    return '<span class="pt-yes">PT ✓</span>' if g["pt"] == "yes" else (
        '<span class="pt-unk">PT ?</span>' if g["pt"] == "unknown" else '<span class="pt-unk">No PT</span>')


def stars(g):
    return f'<span class="star">★ {g["avg_rating"]}</span> <span class="mut">({g["n_reviews"]})</span>' if g.get("n_reviews") else ""


def gmaps(g):
    return f"https://www.google.com/maps/dir/?api=1&destination={g['lat']},{g['lon']}"


def initials_logo(name):
    letters = "".join(w[0] for w in name.split()[:2]).upper()
    return (f"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'>"
            f"<rect width='64' height='64' fill='%23E10600'/><text x='50%' y='58%' font-family='Arial Black' "
            f"font-size='24' fill='white' text-anchor='middle'>{esc(letters)}</text></svg>")


def popup_html(g):
    logo = g["logo_url"] or initials_logo(g["name"])
    chips = "".join(f'<span style="display:inline-block;border:1px solid #ddd;padding:1px 6px;margin:2px;font-size:10px;'
                    f'text-transform:uppercase">{esc(s)}</span>' for s in g["sports"])
    pt = ('<span style="background:#E10600;color:#fff;padding:2px 6px;font-size:10px;font-weight:800">PERSONAL TRAINING ✓</span>'
          if g["pt"] == "yes" else '<span style="color:#888;font-size:10px">PT not confirmed - ask the gym</span>')
    web = (f'<a href="{esc(g["website"])}" target="_blank" style="background:#111;color:#fff;padding:6px 10px;'
           f'text-decoration:none;font-weight:700;font-size:11px;margin-right:4px">VISIT WEBSITE ↗</a>') if g["website"] else ""
    ig = (f'<a href="https://instagram.com/{esc(g["instagram"].lstrip("@").split("/")[-1])}" target="_blank" '
          f'style="font-size:11px;margin-right:6px">Instagram</a>') if g.get("instagram") else ""
    phone = f'<div style="font-size:11px;margin-top:4px">📞 {esc(g["phone"])}</div>' if g.get("phone") else ""
    return f"""
<div style="font-family:Arial;width:260px">
  <div style="display:flex;gap:10px;align-items:center">
    <img src="{logo}" onerror="this.src=&quot;{initials_logo(g['name'])}&quot;"
         style="width:56px;height:56px;object-fit:contain;border-radius:8px;border:1px solid #eee;background:#fff">
    <div><div style="font-weight:900;font-size:15px;line-height:1.1">{esc(g['name'])}</div>
    <div style="color:#666;font-size:11px">{esc(g['city'])} {esc(g['country'])}</div></div>
  </div>
  <div style="margin:6px 0">{pt}</div><div>{chips}</div>
  <div style="font-size:11px;color:#444;margin:6px 0">{esc((g['description'] or '')[:160])}</div>{phone}
  <div style="margin-top:8px">{web}
    <a href="{gmaps(g)}" target="_blank" style="background:#E10600;color:#fff;padding:6px 10px;text-decoration:none;
       font-weight:700;font-size:11px">DIRECTIONS</a></div>
  <div style="margin-top:6px">{ig}<span style="font-size:10px;color:#999">#{g['id']} · {g['source']}</span></div>
</div>"""


def build_map(rows, center=(25, 10), zoom=2, style="Google Streets"):
    tiles = {
        "Google Streets": ("https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", "Google"),
        "Google Satellite": ("https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "Google"),
        "Dark": ("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", "© OpenStreetMap © CARTO"),
    }
    url, attr = tiles[style]
    m = folium.Map(location=center, zoom_start=zoom, tiles=url, attr=attr, control_scale=True, world_copy_jump=True)
    Fullscreen().add_to(m)
    LocateControl(flyTo=True).add_to(m)
    cluster = MarkerCluster(options={"showCoverageOnHover": False, "maxClusterRadius": 45}).add_to(m)
    for g in rows:
        color = RED if g["pt"] == "yes" else "#777"
        ring = "3px solid #C9A227" if g["featured"] else "2px solid #fff"
        icon = folium.DivIcon(html=f'<div style="width:18px;height:18px;border-radius:50%;background:{color};'
                                   f'border:{ring};box-shadow:0 0 0 3px rgba(225,6,0,.25)"></div>',
                              icon_size=(18, 18), icon_anchor=(9, 9))
        folium.Marker([g["lat"], g["lon"]], icon=icon, tooltip=g["name"],
                      popup=folium.Popup(popup_html(g), max_width=290)).add_to(cluster)
    return m


def gym_card(g, key, favs):
    logo = g["logo_url"] or initials_logo(g["name"])
    chips = "".join(f'<span class="chip">{esc(s)}</span>' for s in g["sports"][:4])
    dist = f' · {g["km"]:.1f} km' if "km" in g else ""
    st.markdown(f"""<div class="card"><img src="{logo}"><h4>{esc(g['name'])}</h4>
      <div class="mut">{esc(g['city'])} {esc(g['country'])}{dist} &nbsp; {pt_badge(g)} {stars(g)}</div>
      <div style="clear:both">{chips}</div></div>""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    if g["website"]:
        c1.link_button("Website", g["website"], use_container_width=True)
    c2.link_button("Directions", gmaps(g), use_container_width=True)
    if c3.button("♥ Saved" if g["id"] in favs else "♡ Save", key=f"fav{key}{g['id']}", use_container_width=True):
        db.toggle_fav(DEVICE, g["id"])
        st.rerun()



SPORT_ART = {"Boxing": ("🥊", "#E10600", "#5A0000"), "MMA": ("🤼", "#1E1E1E", "#E10600"),
             "Muay Thai": ("🦵", "#C9A227", "#7A1C00"), "Kickboxing": ("🦶", "#FF5A1F", "#3B0A00"),
             "Brazilian Jiu-Jitsu": ("🥋", "#1546C0", "#0A1A40"), "Wrestling": ("💪", "#7A7A7A", "#1A1A1A"),
             "Judo": ("🥋", "#F2EDE4", "#6B5E4A"), "Karate": ("🥋", "#B22222", "#2A0A0A"),
             "Taekwondo": ("🦶", "#0050A0", "#C00030"), "Krav Maga": ("🛡️", "#3A5F0B", "#0F1A04"),
             "Martial arts": ("⛩️", "#8B0000", "#1A0A0A")}


def wolt_card(g):
    emo, c1, c2 = SPORT_ART.get(g["sports"][0] if g["sports"] else "Martial arts", SPORT_ART["Martial arts"])
    logo = g["logo_url"] or initials_logo(g["name"])
    meta = []
    if g.get("n_reviews"):
        meta.append(f'<span class="star">★</span> {g["avg_rating"]}')
    if "km" in g:
        meta.append(f'{g["km"]:.1f} km')
    meta.append("PT ✓" if g["pt"] == "yes" else "PT ?")
    badge = '<div class="w-badge">LEGENDARY</div>' if g["featured"] else ""
    return f"""<a class="w-card" href="?gym={g['id']}&d={DEVICE}" target="_self">
      <div class="w-cover" style="background:linear-gradient(135deg,{c1},{c2})">{badge}<span>{emo}</span>
        <img class="w-logo" src="{logo}"></div>
      <div class="w-body"><div class="w-name">{esc(g['name'])}</div>
        <div class="w-sub">{esc(' · '.join(g['sports'][:3]))}</div>
        <div class="w-meta">{' · '.join(meta)} · {esc(g['city'])}</div></div></a>"""


def wolt_row(title, rows):
    if rows:
        st.markdown(f'<div class="w-title">{esc(title)}</div><div class="w-row">'
                    + "".join(wolt_card(g) for g in rows[:20]) + "</div>", unsafe_allow_html=True)


st.markdown("""<style>
.w-title {{ font-family:'Anton'; font-size:1.6rem; text-transform:uppercase; margin:1.4rem 0 .6rem; color:var(--bone); }}
.w-row {{ display:flex; gap:16px; overflow-x:auto; padding-bottom:10px; scroll-snap-type:x mandatory; }}
.w-row::-webkit-scrollbar {{ height:6px; }} .w-row::-webkit-scrollbar-thumb {{ background:var(--line); border-radius:3px; }}
.w-card {{ flex:0 0 290px; scroll-snap-align:start; background:var(--card); border-radius:14px; overflow:hidden;
  text-decoration:none !important; border:1px solid var(--line); transition:.18s; }}
.w-card:hover {{ transform:translateY(-3px); border-color:var(--red); box-shadow:0 12px 30px rgba(225,6,0,.15); }}
.w-cover {{ height:150px; position:relative; display:flex; align-items:center; justify-content:center; }}
.w-cover span {{ font-size:4rem; filter:drop-shadow(0 6px 12px rgba(0,0,0,.4)); }}
.w-logo {{ position:absolute; left:14px; bottom:-22px; width:52px; height:52px; border-radius:12px; background:#fff;
  object-fit:contain; border:3px solid var(--card); }}
.w-badge {{ position:absolute; top:10px; left:10px; background:var(--gold); color:#000; font-size:.65rem; font-weight:800;
  padding:3px 8px; border-radius:6px; letter-spacing:.08em; }}
.w-body {{ padding:28px 14px 14px; }}
.w-name {{ color:var(--bone); font-weight:800; font-size:1.02rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.w-sub {{ color:var(--mut); font-size:.82rem; margin-top:2px; }}
.w-meta {{ color:var(--bone); font-size:.8rem; margin-top:8px; border-top:1px solid var(--line); padding-top:8px; }}
.w-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; }}
.w-grid .w-card {{ flex:none; }}
</style>""".replace("{{", "{").replace("}}", "}"), unsafe_allow_html=True)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown('<div class="brand">CORNER<span>STONE</span></div><div class="tag">Combat Club</div>', unsafe_allow_html=True)
    st.write("")
    page = st.radio("Go to", ["🏠 Discover", "🗺️ World map", "📍 Near me", "🔎 Explore", "🌍 Scan a city", "🏟️ Gym page",
                              "➕ Add a gym", "♥ Saved", "ℹ️ About"], label_visibility="collapsed", index=5 if st.query_params.get("gym") else 0)
    st.divider()
    st.caption("FILTERS")
    q = st.text_input("Search name / city", placeholder="e.g. Tiger, Oslo")
    sports = st.multiselect("Sports", db.SPORTS)
    pt_only = st.toggle("Personal training confirmed only", value=False)
    country = st.selectbox("Country", [""] + db.countries(), format_func=lambda c: c or "All countries")
    filters = dict(q=q, sports=sports, pt_only=pt_only, country=country)

favs = db.fav_ids(DEVICE)
s = db.stats()

# ------------------------------------------------------------------ pages
if page == "🏠 Discover":
    top1, top2 = st.columns([1, 2])
    where = top1.text_input("📍 Your area", value=st.session_state.get("where", ""), placeholder="Oslo")
    st.session_state.where = where
    cat = top2.pills("Categories", ["All"] + db.SPORTS, default="All", label_visibility="collapsed")
    flt = dict(filters)
    if cat and cat != "All":
        flt["sports"] = [cat]
    origin = None
    if where:
        try:
            gg = db.geocode(where)
            origin = (gg["lat"], gg["lon"])
        except Exception:
            st.warning("Couldn't find that area.")
    rows = db.nearest(*origin, n=500, **flt) if origin else db.gyms(**flt)
    view = st.segmented_control("View", ["Cards", "Map"], default="Cards", label_visibility="collapsed")
    if view == "Map":
        st_folium(build_map(rows, origin or (25, 10), 12 if origin else 2), height=620,
                  use_container_width=True, returned_objects=[])
    else:
        if origin:
            wolt_row("Closest to you", rows)
            if not rows or rows[0]["km"] > 30:
                st.info("Not many gyms mapped here yet - open **Scan a city** to pull them all in.")
        wolt_row("1-on-1 personal training", [g for g in rows if g["pt"] == "yes"])
        wolt_row("Top rated", sorted([g for g in rows if g.get("n_reviews")], key=lambda g: -g["avg_rating"]))
        wolt_row("Legendary fight camps", [g for g in rows if g["featured"]])
        for sp in ["Muay Thai", "Boxing", "MMA", "Brazilian Jiu-Jitsu"]:
            if not cat or cat == "All":
                wolt_row(f"{sp} gyms", [g for g in rows if sp in g["sports"]])
        st.markdown(f'<div class="w-title">All gyms ({len(rows):,})</div><div class="w-grid">'
                    + "".join(wolt_card(g) for g in rows[:60]) + "</div>", unsafe_allow_html=True)

elif page == "🗺️ World map":
    st.markdown(f"""<div class="hero"><div class="tag">Cornerstone Combat Club</div>
      <h1>Every fight gym.<br><em>Every corner</em> of the earth.</h1>
      <p>Boxing, MMA, Muay Thai, BJJ, wrestling - find gyms that offer personal training,
      tap the pin, see the logo, hit the website.</p></div>""", unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    for col, n, lbl in [(a, s["gyms"], "Gyms mapped"), (b, s["pt"], "PT confirmed"),
                        (c, s["countries"], "Countries"), (d, s["cities"], "Cities scanned")]:
        col.markdown(f'<div class="stat"><b>{n:,}</b><small>{lbl}</small></div>', unsafe_allow_html=True)
    st.write("")
    style = st.segmented_control("Map style", ["Google Streets", "Google Satellite", "Dark"], default="Google Streets")
    rows = db.gyms(**filters)
    center, zoom = ((rows[0]["lat"], rows[0]["lon"]), 11) if (q or country) and rows else ((25, 10), 2)
    st_folium(build_map(rows, center, zoom, style or "Google Streets"), height=640, use_container_width=True,
              returned_objects=[])
    st.caption(f"{len(rows):,} gyms shown · 🔴 PT confirmed · ⚪ PT unknown · gold ring = legendary camp. "
               "Missing your city? Use **Scan a city** to pull every gym OpenStreetMap knows.")

elif page == "📍 Near me":
    st.header("Gyms near you")
    loc = None
    if get_geolocation:
        if st.checkbox("Use my location"):
            res = get_geolocation()
            if res and "coords" in res:
                loc = (res["coords"]["latitude"], res["coords"]["longitude"])
    place = st.text_input("…or type a place", placeholder="Grünerløkka, Oslo")
    if place and not loc:
        try:
            g = db.geocode(place)
            loc = (g["lat"], g["lon"])
        except Exception as e:
            st.error(str(e))
    if loc:
        near = db.nearest(*loc, n=12, **filters)
        if not near or near[0]["km"] > 30:
            st.info("Few gyms in our map here yet.")
            if st.button("Scan this area now", type="primary"):
                with st.spinner("Scanning OpenStreetMap…"):
                    n, _ = db.import_osm(f"{loc[0]},{loc[1]}")
                st.success(f"Added {n} gyms")
                st.rerun()
        left, right = st.columns([1, 1.3])
        with left:
            for g in near:
                gym_card(g, "near", favs)
        with right:
            st_folium(build_map(near, loc, 12), height=700, use_container_width=True, returned_objects=[])

elif page == "🔎 Explore":
    st.header("Explore gyms")
    rows = db.gyms(**filters)
    sort = st.selectbox("Sort by", ["Featured", "Top rated", "Name"])
    if sort == "Top rated":
        rows.sort(key=lambda r: (r["avg_rating"] or 0), reverse=True)
    elif sort == "Name":
        rows.sort(key=lambda r: r["name"])
    st.caption(f"{len(rows):,} results")
    cols = st.columns(3)
    for i, g in enumerate(rows[:90]):
        with cols[i % 3]:
            gym_card(g, "ex", favs)
    if rows:
        df = pd.DataFrame([{k: (", ".join(v) if isinstance(v, list) else v) for k, v in r.items()
                            if k in ("name", "city", "country", "website", "phone", "sports", "pt", "lat", "lon")} for r in rows])
        st.download_button("Download as CSV", df.to_csv(index=False), "cornerstone_gyms.csv", "text/csv")

elif page == "🌍 Scan a city":
    st.header("Scan any city on earth")
    st.write("Pulls **every** boxing, MMA, Muay Thai, BJJ, wrestling & martial-arts gym that OpenStreetMap "
             "has around a place and drops it on the map - with website, phone and logo when available.")
    c1, c2 = st.columns([3, 1])
    place = c1.text_input("City", placeholder="Oslo, Norway")
    radius = c2.slider("Radius km", 5, 60, 25)
    quick = st.pills("Quick picks", ["Oslo", "Bergen", "Stockholm", "London", "Paris", "Berlin", "New York",
                                     "Las Vegas", "Rio de Janeiro", "Bangkok", "Tokyo", "Dubai", "Sydney"])
    target = place or quick
    if st.button(f"Scan {target or '…'}", type="primary", disabled=not target):
        with st.spinner(f"Searching {target} - this can take ~30 s…"):
            try:
                n, g = db.import_osm(target, radius)
                st.success(f"✅ {n} new gyms added around {g['label']}")
                st.balloons()
            except Exception as e:
                st.error(str(e))
    hist = db.imports()
    if hist:
        st.subheader("Already scanned")
        st.dataframe(pd.DataFrame(hist)[["label", "n", "fetched_at"]].rename(
            columns={"label": "Place", "n": "Gyms added", "fetched_at": "When"}), hide_index=True, use_container_width=True)
    st.caption("Data © OpenStreetMap contributors (ODbL). PT is marked 'unknown' until a gym or the community confirms it.")

elif page == "🏟️ Gym page":
    rows = db.gyms(**filters)
    if not rows:
        st.info("No gyms match your filters.")
    else:
        qg = st.query_params.get("gym")
        idx = next((i for i, r in enumerate(rows) if str(r["id"]) == str(qg)), 0)
        pick = st.selectbox("Choose a gym", rows, index=idx, format_func=lambda g: f"{g['name']} - {g['city']} {g['country']}")
        g = db.gym(pick["id"])
        logo = g["logo_url"] or initials_logo(g["name"])
        st.markdown(f"""<div class="hero" style="padding:2rem"><img src="{logo}" style="width:84px;height:84px;background:#fff;
          border-radius:8px;object-fit:contain;float:right"><div class="tag">{esc(g['city'])} · {esc(g['country'])}</div>
          <h1 style="font-size:3rem!important">{esc(g['name'])}</h1>
          <p>{esc(g['description'] or 'Combat sports gym.')}</p>{pt_badge(g)} {stars(g)}<br>
          {''.join(f'<span class="chip">{esc(x)}</span>' for x in g['sports'])}</div>""", unsafe_allow_html=True)
        b1, b2, b3, b4 = st.columns(4)
        if g["website"]:
            b1.link_button("Visit website ↗", g["website"], type="primary", use_container_width=True)
        b2.link_button("Directions", gmaps(g), use_container_width=True)
        if g["phone"]:
            b3.link_button(f"Call {g['phone']}", f"tel:{g['phone']}", use_container_width=True)
        if b4.button("♥ Saved" if g["id"] in favs else "♡ Save", use_container_width=True):
            db.toggle_fav(DEVICE, g["id"])
            st.rerun()
        left, right = st.columns([1, 1])
        with left:
            st_folium(build_map([g], (g["lat"], g["lon"]), 15), height=380, use_container_width=True, returned_objects=[])
            st.subheader("Do they offer personal training?")
            st.caption(f"Community votes - yes: {g['pt_votes_yes']} · no: {g['pt_votes_no']}")
            y, n = st.columns(2)
            if y.button("👊 Yes, they do", use_container_width=True):
                db.vote_pt(g["id"], True); st.toast("Thanks, fighter!"); st.rerun()
            if n.button("✋ No PT here", use_container_width=True):
                db.vote_pt(g["id"], False); st.toast("Noted."); st.rerun()
        with right:
            st.subheader("Reviews")
            with st.form("rev", clear_on_submit=True):
                who = st.text_input("Your name")
                rating = st.slider("Rating", 1, 5, 5)
                txt = st.text_area("How was the session?")
                if st.form_submit_button("Post review", type="primary"):
                    db.add_review(g["id"], who, rating, txt); st.rerun()
            for r in db.reviews(g["id"]):
                st.markdown(f'<div class="card"><span class="star">{"★" * r["rating"]}</span> <b>{esc(r["author"])}</b>'
                            f'<div class="mut">{esc(r["text"])}</div></div>', unsafe_allow_html=True)

elif page == "➕ Add a gym":
    st.header("Put a gym on the map")
    with st.form("add"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Gym name *")
        website = c2.text_input("Website", placeholder="https://")
        place = c1.text_input("Address or city *", placeholder="Storgata 1, Oslo")
        phone = c2.text_input("Phone")
        sp = st.multiselect("Sports", db.SPORTS)
        pt = st.radio("Offers personal training?", ["yes", "unknown", "no"], horizontal=True)
        ig = st.text_input("Instagram handle")
        desc = st.text_area("Short description")
        if st.form_submit_button("Add gym", type="primary"):
            try:
                g = db.geocode(place)
                db.add_gym(name, g["lat"], g["lon"], place.split(",")[-1].strip(), g["cc"], website, sp, desc, pt,
                           address=place, phone=phone, instagram=ig)
                st.success(f"{name} is live on the map 🥊")
            except Exception as e:
                st.error(str(e))

elif page == "♥ Saved":
    st.header("Your saved gyms")
    rows = [g for g in db.gyms(limit=100000) if g["id"] in favs]
    if not rows:
        st.info("Tap ♡ Save on any gym to build your fight-trip list.")
    else:
        st.caption("Bookmark this page URL to keep your list on this device.")
        st_folium(build_map(rows), height=420, use_container_width=True, returned_objects=[])
        cols = st.columns(3)
        for i, g in enumerate(rows):
            with cols[i % 3]:
                gym_card(g, "fav", favs)

else:
    st.header("About Cornerstone Combat Club")
    st.markdown("""
**Cornerstone** is the world map of combat-sports gyms that train you one-on-one.

- **Legendary camps** are hand-picked (gold ring) - Tiger Muay Thai, Evolve, AKA, Tristar, SBG and more.
- **Every other gym** comes live from OpenStreetMap - scan any city and they appear instantly.
- **PT status** is crowd-verified: tap *Yes / No* on a gym page. Red pins = personal training confirmed.
- **Logos** are pulled from each gym's own website icon. No website? We draw a monogram.

*Always confirm prices and availability directly with the gym. Seed coordinates are approximate.*
""")
