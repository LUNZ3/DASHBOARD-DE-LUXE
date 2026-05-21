import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

# Hindrer tidssone-kræsj i skyen
yf.set_tz_cache_location('/tmp/yf-tz-cache')

st.set_page_config(page_title="Investor Dashboard - Oslo Børs", layout="wide")
st.title("📊 Aksjedashboard: Oslo Børs & Makro")

# Legg inn selskapsinfo manuelt (Ticker, Fullt navn, og Omsetning i NOK)
selskaps_data = {
    "DNO": {
        "ticker": "DNO.OL",
        "navn": "DNO ASA",
        "omsetning": "ca. 13,2 milliarder NOK (2024)"
    },
    "Endúr": {
        "ticker": "ENDUR.OL",
        "navn": "Endúr ASA",
        "omsetning": "ca. 2,5 milliarder NOK (2024)"
    },
    "Nordic Semiconductor": {
        "ticker": "NOD.OL",
        "navn": "Nordic Semiconductor ASA",
        "omsetning": "ca. 12,8 milliarder NOK (2024)"
    },
    "Brent Oil": {
        "ticker": "BZ=F",
        "navn": "Brent Crude Oil Future",
        "omsetning": "N/A (Råvare)"
    }
}

# Sidebar for valg av selskap
selected_name = st.sidebar.selectbox("Velg selskap/data:", list(selskaps_data.keys()))

# Hent ut infoen basert på valget
valgt_info = selskaps_data[selected_name]
ticker_symbol = valgt_info["ticker"]

# Sikker funksjon for å hente KUN kurshistorikk (ingen info-kall!)
@st.cache_data(ttl=3600)
def get_historical_data(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    return hist

# Prøv å hente historikken
try:
    hist = get_historical_data(ticker_symbol)
    
    # Vis selskapsinfo øverst i appen
    st.header(f"{valgt_info['navn']} ({selected_name})")
    
    # Lag to kolonner: Én for omsetning/nøkkeltall, én for grafen
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("📋 Selskapsinfo")
        st.write(f"**Ticker på Børs:** {ticker_symbol}")
        st.write(f"**Årlig omsetning:** {valgt_info['omsetning']}")
        
        if not hist.empty:
            siste_kurs = hist['Close'].iloc[-1]
            forrige_kurs = hist['Close'].iloc[-2]
            endring = siste_kurs - forrige_kurs
            prosent = (endring / forrige_kurs) * 100
            st.metric(label="Siste Sluttkurs", value=f"{siste_kurs:.2f}", delta=f"{endring:.2f} ({prosent:.2f}%)")

    with col2:
        if not hist.empty:
            st.subheader("📈 Kursutvikling siste år")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', name='Sluttkurs', line=dict(color='#00FFCC', width=2)))
            fig.update_layout(
                template="plotly_dark",
                margin=dict(l=20, r=20, t=20, b=20),
                xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Fant ingen kursdata for dette symbolet akkurat nå.")

except Exception as e:
    st.error(f"Klarte ikke å hente tekniske kursdata: {e}")
