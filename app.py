import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import warnings
import time  # <-- Tambahan wajib untuk fitur jeda waktu (anti-ban)
warnings.filterwarnings('ignore')

st.set_page_config(page_title="IDX Technical Screener", layout="wide", page_icon="📈")

st.title("📈 IDX Technical Screener - Fibonacci & Price Action")
st.markdown("Screener khusus untuk memindai saham yang mendekati level Fibonacci Support dengan konfirmasi Volume (VPA), EMA, VWAP, dan pola Bullish Engulfing.")

# === SIDEBAR PENGATURAN ===
st.sidebar.header("Parameter Screener")
default_tickers = "ACES, ADRO, AKRA, ANTM, AUTO, BRIS, BRMS, BSDE, CMRY, CPIN, CTRA, ELSA, ENRG, ERAA, EXCL, HEAL, HRUM, ICBP, INDY, INDF, INKP, INTP, ITMG, JPFA, JSMR, KLBF, LSIP, MAPI, MDKA, MEDC, MIKA, MNCN, MTEL, PGAS, POWR, PTBA, PWON, SIDO, SMGR, SRTG, SSIA, TAPG, TKIM, TLKM, TPIA, UNTR, UNVR, BUMI"
tickers_input = st.sidebar.text_input("Daftar Emiten (pisahkan dengan koma):", default_tickers)

# UPDATE: Pilihan periode diubah menjadi 3 Bulan, 6 Bulan, dan 1 Tahun
period_map = {"3 Bulan": "3mo", "6 Bulan": "6mo", "1 Tahun": "1y"}
selected_period_label = st.sidebar.selectbox("Periode Data:", list(period_map.keys()), index=1)
period = period_map[selected_period_label]

fibo_tolerance = st.sidebar.slider("Toleransi Kedekatan dgn Fibo (%)", 1.0, 5.0, 3.0) / 100.0

# Membersihkan input ticker dan menambahkan suffix .JK untuk bursa Indonesia
ticker_list = [t.strip().upper() for t in tickers_input.split(",")]
idx_tickers = [f"{t}.JK" if not t.endswith(".JK") else t for t in ticker_list]

@st.cache_data(ttl=3600)
def fetch_data(symbol, period):
    df = yf.download(symbol, period=period, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1) # Menangani format multi-index yfinance versi baru
    return df

def calculate_indicators(df):
    df = df.copy()
    # UPDATE: Batas minimum data diturunkan agar periode 3mo bisa lolos
    if df.empty or len(df) < 25: 
        return df
    
    # 1. EMA (Ditambahkan fallback agar tidak error jika data kurang dari 50 baris)
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    if len(df) >= 50:
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    else:
        df['EMA_50'] = df['EMA_20']
    
    # 2. VWAP (Pendekatan dengan rolling 20 hari atau sesuai jumlah data)
    window_vwap = min(20, len(df))
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP_20d'] = (typical_price * df['Volume']).rolling(window_vwap).sum() / df['Volume'].rolling(window_vwap).sum()
    
    # 3. Fibonacci Retracement (Berdasarkan periode data yang ditarik)
    swing_high = df['High'].max()
    swing_low = df['Low'].min()
    diff = swing_high - swing_low
    
    df['Fib_236'] = swing_high - 0.236 * diff
    df['Fib_382'] = swing_high - 0.382 * diff
    df['Fib_500'] = swing_high - 0.500 * diff
    df['Fib_618'] = swing_high - 0.618 * diff
    df['Fib_786'] = swing_high - 0.786 * diff
    
    # 4. Candlestick - Bullish Engulfing
    df['Bullish_Engulfing'] = False
    for i in range(1, len(df)):
        prev_open = float(df['Open'].iloc[i-1])
        prev_close = float(df['Close'].iloc[i-1])
        curr_open = float(df['Open'].iloc[i])
        curr_close = float(df['Close'].iloc[i])
        
        # Syarat: Candle kemarin merah, hari ini hijau dan body menelan body kemarin
        if (prev_close < prev_open) and (curr_close > curr_open) and \
           (curr_open <= prev_close) and (curr_close >= prev_open):
            df.iloc[i, df.columns.get_loc('Bullish_Engulfing')] = True
            
    # 5. Volume Price Analysis (VPA) - Volume Drying Up
    window_vol = min(20, len(df))
    df['Vol_SMA_20'] = df['Volume'].rolling(window_vol).mean()
    df['Vol_Drying'] = df['Volume'] < df['Vol_SMA_20']
    
    return df

st.write(f"Menganalisis **{len(ticker_list)}** saham... Silakan tunggu.")

results = []
all_data = {}

# === PROSES SCREENING (DENGAN ANTI-BAN & PROGRESS BAR) ===
progress_bar = st.progress(0)
status_text = st.empty()
total_tickers = len(ticker_list)

for i, (ticker, symbol) in enumerate(zip(ticker_list, idx_tickers)):
    status_text.text(f"Memproses {i+1}/{total_tickers} : Menarik data {ticker}...")
    
    try:
        df = fetch_data(symbol, period)
        if df.empty:
            time.sleep(1.5) # Tetap beri jeda meskipun data kosong agar loop selaras
            progress_bar.progress((i + 1) / total_tickers)
            continue
        
        df = calculate_indicators(df)
        all_data[ticker] = df
        
        latest = df.iloc[-1]
        close_price = float(latest['Close'])
        
        # Mengecek apakah harga terakhir dekat dengan level Fibo Krusial (38.2, 50.0, atau 61.8)
        near_fib = False
        closest_fib_name = "-"
        for fib_name in ['Fib_382', 'Fib_500', 'Fib_618']:
            fib_val = float(latest[fib_name])
            if abs(close_price - fib_val) / fib_val <= fibo_tolerance:
                near_fib = True
                # Perbaikan 1: Konversi "382" menjadi float lalu dibagi 10 agar jadi 38.2
                angka_fibo = float(fib_name.replace("Fib_", "")) / 10
                closest_fib_name = f"{angka_fibo:.1f}"
                break
                
        # Jika memenuhi salah satu sinyal teknikal
        if near_fib or latest['Bullish_Engulfing']:
            results.append({
                "Emiten": ticker,
                # Perbaikan 2: Konversi ke integer (bilangan bulat) agar tidak ada koma panjang
                "Harga Terakhir": int(round(close_price, 0)),
                "Dekat Fibo": f"{closest_fib_name}%" if near_fib else "Tidak",
                "Bullish Engulfing": "Ya" if latest['Bullish_Engulfing'] else "Tidak",
                "Vol Drying (VPA)": "Ya" if latest['Vol_Drying'] else "Tidak",
                "> VWAP 20d": "Ya" if close_price > latest['VWAP_20d'] else "Tidak",
                "> EMA 20": "Ya" if close_price > latest['EMA_20'] else "Tidak"
            })
    except Exception as e:
        pass # Lewati jika ada error pada ticker tertentu
        
    # Jeda 1.5 detik agar aman dari blokir Yahoo Finance
    time.sleep(1.5)
    
    # Update progress bar
    progress_bar.progress((i + 1) / total_tickers)

status_text.text("✅ Penarikan data selesai!")

# === MENAMPILKAN HASIL SCREENER ===
if results:
    st.success("✅ Screener selesai! Berikut saham yang masuk kriteria pantauan:")
    result_df = pd.DataFrame(results)
    # Menambahkan warna untuk tabel
    def highlight_yes(val):
        color = '#a8f0c6' if val == 'Ya' else ''
        return f'background-color: {color}'
    
    st.dataframe(result_df.style.map(highlight_yes, subset=['Bullish Engulfing', 'Vol Drying (VPA)', '> VWAP 20d', '> EMA 20']), use_container_width=True)
else:
    st.info("ℹ️ Saat ini belum ada saham yang memenuhi kriteria setup dari daftar yang Anda masukkan.")

st.markdown("---")

# === VISUALISASI CHART ===
st.subheader("📊 Bedah Chart Teknikal")
selected_ticker = st.selectbox("Pilih Emiten untuk melihat pergerakan harganya:", ticker_list)

if selected_ticker in all_data:
    chart_df = all_data[selected_ticker].dropna()
    
    fig = go.Figure()
    
    # Trace Candlestick
    fig.add_trace(go.Candlestick(
        x=chart_df.index,
        open=chart_df['Open'],
        high=chart_df['High'],
        low=chart_df['Low'],
        close=chart_df['Close'],
        name='Harga',
        increasing_line_color='cyan', decreasing_line_color='red'
    ))
    
    # Trace EMA & VWAP
    fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['EMA_20'], line=dict(color='yellow', width=1.5), name='EMA 20'))
    fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df['VWAP_20d'], line=dict(color='magenta', width=1.5, dash='dot'), name='VWAP 20d'))
    
    # Trace Garis Fibonacci
    latest = chart_df.iloc[-1]
    colors = ['gray', 'orange', 'yellow', 'lime', 'red']
    levels = [0.236, 0.382, 0.500, 0.618, 0.786]
    fib_vals = [latest['Fib_236'], latest['Fib_382'], latest['Fib_500'], latest['Fib_618'], latest['Fib_786']]
    
    for val, level, col in zip(fib_vals, levels, colors):
        fig.add_hline(y=val, line_dash="dash", line_color=col, annotation_text=f" Fibo {level*100:.1f}% ", annotation_position="top left", annotation_font_color=col)
        
    fig.update_layout(
        title=f"Pergerakan {selected_ticker} & Level Fibonacci",
        yaxis_title="Harga (Rupiah)",
        xaxis_title="Tanggal",
        template="plotly_dark",
        height=650,
        margin=dict(l=50, r=50, b=50, t=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    # Menghilangkan range slider bawaan plotly agar lebih luas
    fig.update_xaxes(rangeslider_visible=False)
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.caption("Garis horizontal putus-putus mewakili level Fibonacci Support/Resistance. Gunakan VPA dan Bullish Engulfing dari tabel screener untuk konfirmasi titik pantul.")
