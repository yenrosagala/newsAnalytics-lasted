import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from app.core.config import Config
from app.core.logger import setup_logger
from app.core.auth import render_auth_sidebar
from app.components.sidebar import load_custom_css, render_app_sidebar
from app import api_bridge
from app.services.database_service import DatabaseConnectionError

config = Config()
logger = setup_logger("page_predictive")

# Konfigurasi Halaman[cite: 18]
st.set_page_config(page_title="Predictive Intelligence", layout="wide", page_icon="🔮")

load_custom_css()
render_app_sidebar(active_page="pages/4_Predictive_Intelligence.py")
render_auth_sidebar()

st.markdown("# 🔮 Predictive Intelligence")
st.caption("Trend Detection · Forecasting · Anomaly Detection (Terintegrasi API)")
st.markdown("Analisis pola volume & sentimen berita dari waktu ke waktu...[cite: 18]")
st.markdown("---")

SEVERITY_COLORS = {"Tinggi": "#ef4444", "Sedang": "#f59e0b", "Rendah": "#10b981"}
_DARK_LAYOUT = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font_color="#1a2233", title_font_color="#1a2233", margin=dict(t=30, b=10, l=10, r=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

@st.cache_data(ttl=120)
def _get_available_keywords():
    """Returns (keywords, error_message)."""
    try:
        df = pd.DataFrame(api_bridge.get_articles(limit=1000))
        keywords = sorted(df['kata_kunci'].dropna().unique()) if not df.empty and 'kata_kunci' in df.columns else []
        return keywords, None
    except DatabaseConnectionError as e:
        return [], str(e)
    except Exception as e:
        return [], f"Terjadi kesalahan tak terduga: {e}"

available_keywords, keywords_error = _get_available_keywords()

if not available_keywords:
    if keywords_error:
        st.error(f"⚠️ Gagal memuat data dari database — ini BUKAN 'tidak ada keyword', koneksi/query-nya gagal: {keywords_error}")
    else:
        st.warning("Belum ada data berita tersimpan untuk dianalisis. Jalankan scraping terlebih dahulu.")
    st.stop()

col_select, col_config = st.columns([2, 1])
with col_select:
    selected_keyword = st.selectbox("🔖 Pilih Keyword untuk Dianalisis", options=available_keywords, key="predictive_keyword_select")
with col_config:
    forecast_horizon = st.slider("Horizon Forecast (hari)", min_value=3, max_value=14, value=7, key="predictive_horizon")

# --- AMBIL DATA ANALITIK DARI BACKEND ---
with st.spinner("Memuat analitik dari backend..."):
    try:
        data = api_bridge.get_predictive_analysis(selected_keyword, forecast_horizon=forecast_horizon)
        trend_info = data.get("trend_info", {})
        alerts = data.get("alerts", [])
        anomalies_df = pd.DataFrame(data.get("anomalies", []))
        forecast = data.get("forecast")
        daily_volume_data = data.get("daily_volume", {}) # Pastikan API mengirimkan historical volume plot data
    except Exception as e:
        st.error(f"Gagal menghubungi server: {e}")
        st.stop()

tab_alerts, tab_trend, tab_forecast, tab_anomaly = st.tabs(["🔔 Alerts", "📈 Trend Detection", "🔮 Forecasting", "🚨 Anomaly Detection"])

# ==================== TAB 1: ALERTS ====================
with tab_alerts:
    st.markdown("### 🔔 Ringkasan Peringatan")
    if not alerts:
        st.success(f"✅ Tidak ada peringatan signifikan untuk '{selected_keyword}' saat ini.")
    else:
        for a in alerts:
            color = SEVERITY_COLORS.get(a["severity"], "#64748b")
            icon = "🚨" if a["type"] == "anomaly" else "📊"
            st.markdown(f"<div style='background:{color}15; border-left:4px solid {color}; padding:10px 14px; border-radius:6px; margin-bottom:8px;'><b>{icon} [{a['severity']}]</b> {a['message']}</div>", unsafe_allow_html=True)

    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Arah Tren", trend_info.get("direction", "Stabil"), f"{trend_info.get('pct_change', 0):+.0f}%")
    m2.metric("Rata-rata 7 Hari Terakhir", f"{trend_info.get('recent_avg', 0):.1f} artikel/hari")
    m3.metric("Anomali Terdeteksi", int(anomalies_df["is_anomaly"].sum()) if not anomalies_df.empty else 0)

# ==================== TAB 2: TREND DETECTION ====================
with tab_trend:
    st.markdown("### 📈 Volume Berita (Render via Backend Data)")
    if "date" in daily_volume_data and "count" in daily_volume_data:
        dates = daily_volume_data["date"]
        counts = daily_volume_data["count"]
        ma7_counts = daily_volume_data.get("ma7_count", counts)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=dates, y=counts, name="Volume Harian", marker_color="rgba(56,189,248,0.35)"))
        fig.add_trace(go.Scatter(x=dates, y=ma7_counts, name="Moving Average (7 hari)", line=dict(color="#2563eb", width=2.5)))
        fig.update_layout(xaxis_title="Tanggal", yaxis_title="Jumlah Artikel", **_DARK_LAYOUT)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("Historical data timeline chart belum tersedia dari API.")

# ==================== TAB 3: FORECASTING ====================
with tab_forecast:
    st.markdown(f"### 🔮 Proyeksi {forecast_horizon} Hari ke Depan[cite: 18]")
    if not forecast:
        st.info("Data historis terlalu sedikit untuk membuat proyeksi yang bermakna (minimal ~5 hari data).")
    else:
        fig_fc = go.Figure()
        if "date" in daily_volume_data:
            fig_fc.add_trace(go.Scatter(x=daily_volume_data["date"], y=daily_volume_data["count"], name="Data Historis", line=dict(color="#2563eb")))
        
        fig_fc.add_trace(go.Scatter(x=forecast["forecast_dates"], y=forecast["forecast_values"], name="Proyeksi", line=dict(color="#f59e0b", dash="dot")))
        fig_fc.add_trace(go.Scatter(
            x=list(forecast["forecast_dates"]) + list(forecast["forecast_dates"][::-1]),
            y=list(forecast["upper_band"]) + list(forecast["lower_band"][::-1]),
            fill="toself", fillcolor="rgba(245,158,11,0.15)", line=dict(color="rgba(0,0,0,0)"), name="Confidence Band (95%)",
        ))
        fig_fc.update_layout(xaxis_title="Tanggal", yaxis_title="Jumlah Artikel", **_DARK_LAYOUT)
        st.plotly_chart(fig_fc, width='stretch')

        slope = forecast["slope_per_day"]
        direction_word = "naik" if slope > 0.1 else "turun" if slope < -0.1 else "relatif stabil"
        st.caption(f"⚠️ **Catatan metodologi**: Proyeksi ini memakai regresi linear...[cite: 18]")

# ==================== TAB 4: ANOMALY DETECTION ====================
with tab_anomaly:
    st.markdown("### 🚨 Deteksi Anomali Volume Berita")
    if anomalies_df.empty:
        st.info("Belum cukup data untuk deteksi anomali.")
    else:
        anomalies_df['tanggal'] = pd.to_datetime(anomalies_df['tanggal'])
        fig_anom = go.Figure()
        normal_pts = anomalies_df[~anomalies_df["is_anomaly"]]
        anomaly_pts = anomalies_df[anomalies_df["is_anomaly"]]

        fig_anom.add_trace(go.Scatter(x=normal_pts["tanggal"], y=normal_pts["nilai"], mode="markers+lines", name="Normal", line=dict(color="#2563eb"), marker=dict(size=6)))
        fig_anom.add_trace(go.Scatter(x=anomaly_pts["tanggal"], y=anomaly_pts["nilai"], mode="markers", name="Anomali", marker=dict(size=13, color="#ef4444", symbol="x")))
        fig_anom.update_layout(xaxis_title="Tanggal", yaxis_title="Jumlah Artikel", **_DARK_LAYOUT)
        st.plotly_chart(fig_anom, width='stretch')

        if not anomaly_pts.empty:
            st.markdown("#### Detail Hari Anomali")
            display_df = anomaly_pts[["tanggal", "nilai", "rolling_median", "robust_z_score", "arah"]].copy()
            display_df["tanggal"] = display_df["tanggal"].dt.strftime("%d %b %Y")
            display_df.columns = ["Tanggal", "Jumlah Artikel", "Median Normal", "Skor Z (robust)", "Arah"]
            st.dataframe(display_df, width='stretch', hide_index=True)
        else:
            st.success("✅ Tidak ada anomali terdeteksi pada periode ini.")