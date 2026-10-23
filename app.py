import csv
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="MedAI – Studiehjelp for medisinstudenter",
    page_icon="🩺",
    layout="wide",
)

# ---------- Stil ----------
st.markdown(
    """
    <style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {padding-top: 2rem; max-width: 1150px;}
    .hero {
        background: linear-gradient(135deg, #0f766e 0%, #0e7490 55%, #1e3a8a 100%);
        color: white; padding: 4rem 2.5rem; border-radius: 20px; text-align: center;
        margin-bottom: 2rem;
    }
    .hero h1 {font-size: 3.2rem; margin: 0 0 .5rem 0; color: white;}
    .hero p {font-size: 1.25rem; opacity: .92; max-width: 700px; margin: 0 auto;}
    .card {
        border: 1px solid rgba(128,128,128,.25); border-radius: 16px;
        padding: 1.6rem; height: 100%;
        background: rgba(128,128,128,.06);
    }
    .card h3 {margin-top: 0;}
    .icon {font-size: 2.4rem; margin-bottom: .4rem;}
    .stat {text-align: center; padding: 1rem;}
    .stat .num {font-size: 2.6rem; font-weight: 800; color: #0f766e;}
    .stat .lbl {opacity: .75;}
    .section-title {text-align: center; margin: 3rem 0 1.5rem 0;}
    .footer {text-align: center; opacity: .6; margin-top: 3rem; font-size: .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Hero ----------
st.markdown(
    """
    <div class="hero">
        <h1>🩺 MedAI</h1>
        <p>Bli bedre forberedt til eksamen med hjelp fra ferdige medisinstudenter,
        ferdige slideshows og over 2000 notater om medisin.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns([1, 1, 1])
with c2:
    st.link_button("Kontakt oss ↓", "#kontakt-oss", use_container_width=True, type="primary")

# ---------- Tall ----------
st.write("")
s1, s2, s3 = st.columns(3)
for col, num, lbl in [
    (s1, "2000+", "ferdige notater"),
    (s2, "1:1", "personlig tutoring"),
    (s3, "100%", "laget av medisinstudenter"),
]:
    col.markdown(
        f'<div class="stat"><div class="num">{num}</div><div class="lbl">{lbl}</div></div>',
        unsafe_allow_html=True,
    )

# ---------- Tjenester ----------
st.markdown('<h2 class="section-title">Våre tjenester</h2>', unsafe_allow_html=True)

t1, t2, t3 = st.columns(3)
with t1:
    st.markdown(
        """
        <div class="card">
            <div class="icon">👩‍⚕️</div>
            <h3>1:1 Tutoring</h3>
            <p>Personlig undervisning med ferdige medisinstudenter som har vært gjennom
            pensum selv. Få hjelp med akkurat de temaene du sliter med, i ditt tempo.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t2:
    st.markdown(
        """
        <div class="card">
            <div class="icon">📊</div>
            <h3>Slideshows</h3>
            <p>Ryddige, visuelle presentasjoner som forklarer vanskelige temaer enkelt –
            perfekt for repetisjon og for å få oversikt før eksamen.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t3:
    st.markdown(
        """
        <div class="card">
            <div class="icon">📚</div>
            <h3>2000 ferdige notater</h3>
            <p>Et stort bibliotek med ferdige notater i medisin. Spar timevis med
            skriving og fokuser på å lære i stedet.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------- Slik fungerer det ----------
st.markdown('<h2 class="section-title">Slik fungerer det</h2>', unsafe_allow_html=True)

h1, h2, h3 = st.columns(3)
h1.markdown("### 1️⃣ Ta kontakt\nFortell oss hva du trenger hjelp med.")
h2.markdown("### 2️⃣ Velg tjeneste\nTutoring, slideshows, notater – eller en kombinasjon.")
h3.markdown("### 3️⃣ Kom i gang\nVi setter opp en plan som passer deg og eksamensdatoene dine.")

# ---------- Hvorfor MedAI ----------
st.markdown('<h2 class="section-title">Hvorfor MedAI?</h2>', unsafe_allow_html=True)

w1, w2 = st.columns(2)
with w1:
    st.success("✅ Undervisning fra folk som faktisk har bestått")
    st.success("✅ Fleksibelt – tilpasset din timeplan")
with w2:
    st.success("✅ Oversiktlig og effektivt materiell")
    st.success("✅ Alt samlet på ett sted")

# ---------- FAQ ----------
st.markdown('<h2 class="section-title">Vanlige spørsmål</h2>', unsafe_allow_html=True)

with st.expander("Hvem er tutorene?"):
    st.write("Ferdige medisinstudenter som kan pensum og vet hva som kreves på eksamen.")
with st.expander("Hvilke temaer dekker notatene?"):
    st.write("Over 2000 notater som dekker et bredt spekter av medisinske emner.")
with st.expander("Hvordan booker jeg tutoring?"):
    st.write("Send oss en melding via kontaktskjemaet under, så tar vi kontakt.")
with st.expander("Hva koster det?"):
    st.write("Ta kontakt for en prat om hva du trenger, så får du et tilbud.")

# ---------- Kontakt ----------
st.markdown('<a id="kontakt-oss"></a>', unsafe_allow_html=True)
st.markdown('<h2 class="section-title">Kontakt oss</h2>', unsafe_allow_html=True)

MESSAGES_FILE = Path("meldinger.csv")

left, right = st.columns([3, 2])
with left:
    with st.form("kontakt", clear_on_submit=True):
        name = st.text_input("Navn")
        email = st.text_input("E-post")
        interest = st.multiselect(
            "Hva er du interessert i?",
            ["1:1 Tutoring", "Slideshows", "Ferdige notater", "Annet"],
        )
        message = st.text_area("Melding", height=140)
        sent = st.form_submit_button("Send melding", type="primary")

    if sent:
        if not name.strip() or "@" not in email or not message.strip():
            st.error("Fyll inn navn, gyldig e-post og en melding.")
        else:
            new_file = not MESSAGES_FILE.exists()
            with MESSAGES_FILE.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(["tidspunkt", "navn", "epost", "interesse", "melding"])
                writer.writerow(
                    [datetime.now().isoformat(timespec="seconds"), name, email,
                     ", ".join(interest), message]
                )
            st.success("Takk! Vi tar kontakt så snart som mulig. 🙌")

with right:
    st.markdown(
        """
        <div class="card">
            <h3>Kontaktinfo</h3>
            <p>📧 post@medai.no<br>
            📱 +47 000 00 000<br>
            📍 Oslo, Norge</p>
            <p style="opacity:.7">(Bytt ut med ekte kontaktinfo)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div class="footer">© {datetime.now().year} MedAI. Alle rettigheter forbeholdt.</div>',
    unsafe_allow_html=True,
)
