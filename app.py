import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

# Dette fjerner rate-limiten i skyen uten ekstra pakker
yf.set_tz_cache_location('/tmp/yf-tz-cache')


st.set_page_config(page_title="Investor Dashboard - Oslo Børs", layout="wide")
st.title("📊 Aksjedashboard: Oslo Børs & Makro")

tickers = {
    "DNO": "DNO.OL",
    "Endúr": "ENDUR.OL",
    "Nordic Semiconductor": "NOD.OL",
    "Brent Oil": "BZ=F"
}

selected_name = st.sidebar.selectbox("Velg selskap/data:", list(tickers.keys()))
ticker_symbol = tickers[selected_name]

@st.cache_data(ttl=3600)
def get_data(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1y")
    info = ticker.info
    if not hist.empty:
        hist.index = hist.index.tz_localize(None)
    return hist, info

hist, info = get_data(ticker_symbol)

if hist.empty:
    st.error(f"Kunne ikke hente data for {selected_name}.")
else:
    currency = info.get("currency", "NOK")
    col1, col2, col3, col4 = st.columns(4)

    current_price = hist['Close'].iloc[-1]
    prev_price = hist['Close'].iloc[-2]
    change = ((current_price - prev_price) / prev_price) * 100

    with col1:
        st.metric("Kurs", f"{current_price:.2f} {currency}", f"{change:.2f}%")

    if selected_name != "Brent Oil":
        market_cap = info.get('marketCap')
        revenue = info.get('totalRevenue')
        with col2:
            st.metric("Market Cap", f"{market_cap / 1e9:.2f} mrd" if market_cap else "N/A")
        with col3:
            pe = info.get('trailingPE')
            st.metric("P/E (Trailing)", f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A")
        with col4:
            st.metric("Omsetning (TTM)", f"{revenue / 1e9:.2f} mrd" if revenue else "N/A")
    else:
        with col2:
            st.metric("Type", "Commodity / Makro")

    st.subheader(f"Kursutvikling for {selected_name}")
    fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    if selected_name != "Brent Oil":
        st.subheader("Selskapets KPI & Resultat")
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**Finansiell oversikt:**")
            def to_pct(val):
                return f"{val * 100:.2f}%" if isinstance(val, (int, float)) else "N/A"
            st.json({
                "EBITDA Margin": to_pct(info.get("ebitdaMargins")),
                "Profit Margin": to_pct(info.get("profitMargins")),
                "Return on Equity": to_pct(info.get("returnOnEquity")),
                "Dividend Yield": to_pct(info.get("dividendYield"))
            })
