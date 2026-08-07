import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px

from app.core.config import Config
from app.core.logger import setup_logger
from app.core.auth import render_auth_sidebar
from app.components.sidebar import load_custom_css, render_app_sidebar
from app import api_bridge
from app.services.database_service import DatabaseConnectionError

config = Config()
logger = setup_logger("page_dashboard")

# Konfigurasi Halaman[cite: 16]
st.set_page_config(page_title="Analytics", layout="wide", page_icon="📊")

load_custom_css()
render_app_sidebar(active_page="pages/2_Dashboard.py")
render_auth_sidebar()

st.markdown("# 📊 Analytics Dashboard")
st.caption("Dashboard and Admin Management (Terintegrasi API)")
st.markdown("---")

is_admin = st.session_state.get("role") == "admin"

@st.cache_data(ttl=60)
def load_dashboard_data():
    """Mengambil data artikel dari database. Mengembalikan (df, error_message)."""
    try:
        return pd.DataFrame(api_bridge.get_articles(limit=1000)), None
    except DatabaseConnectionError as e:
        logger.error(f"Gagal mengambil data (koneksi database): {e}")
        return pd.DataFrame(), str(e)
    except Exception as e:
        logger.error(f"Gagal mengambil data: {e}")
        return pd.DataFrame(), f"Terjadi kesalahan tak terduga: {e}"

df_raw, load_error = load_dashboard_data()

date_col = "published_date" if "published_date" in df_raw.columns else ("waktu_tampilan" if "waktu_tampilan" in df_raw.columns else None)
if not df_raw.empty and date_col:
    df_raw[date_col] = pd.to_datetime(df_raw[date_col], errors="coerce")
    if df_raw[date_col].dt.tz is not None:
        df_raw[date_col] = df_raw[date_col].dt.tz_localize(None)
    df_raw["tanggal_saja"] = df_raw[date_col].dt.date

if df_raw.empty:
    if load_error:
        st.error(f"⚠️ Gagal memuat data dari database — ini BUKAN 'belum ada data', koneksi/query-nya gagal: {load_error}")
    else:
        st.info("Basis data terhubung dengan baik, tapi belum ada artikel yang tersimpan. Jalankan scraping terlebih dahulu.")
    st.stop()

col_keyword = "kata_kunci" if "kata_kunci" in df_raw.columns else "keyword"
col_media = "media" if "media" in df_raw.columns else "source"
col_content = "isi_konten" if "isi_konten" in df_raw.columns else "content"
col_title = "judul" if "judul" in df_raw.columns else "title"
col_sentiment = "Sentimen" if "Sentimen" in df_raw.columns else ("sentiment" if "sentiment" in df_raw.columns else None)

# --- CONTROL PANEL FILTER ---
with st.expander("⚙️ Control Panel Data (Filter Global)", expanded=True):
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        available_options = list(df_raw[col_keyword].dropna().unique()) if col_keyword in df_raw.columns else []
        selected_keyword = st.multiselect("Filter Keyword", options=available_options, default=None)
    with f_col2:
        opsi_sentimen = list(df_raw[col_sentiment].dropna().unique()) if col_sentiment else ["POSITIVE", "NEGATIVE", "NEUTRAL"]
        selected_sentimen = st.multiselect("Filter Sentimen", options=opsi_sentimen, default=opsi_sentimen)
    with f_col3:
        opsi_media = list(df_raw[col_media].dropna().unique()) if col_media in df_raw.columns else []
        selected_media = st.multiselect("Filter Media", options=opsi_media, default=None)

filtered_df = df_raw.copy()
if selected_keyword:
    filtered_df = filtered_df[filtered_df[col_keyword].isin(selected_keyword)]
if selected_media:
    filtered_df = filtered_df[filtered_df[col_media].isin(selected_media)]
if col_sentiment and selected_sentimen:
    filtered_df = filtered_df[filtered_df[col_sentiment].isin(selected_sentimen)]

st.caption(f"📋 {len(filtered_df):,} dari {len(df_raw):,} artikel cocok dengan filter saat ini[cite: 16].")

tab_labels = ["📊 Overview", "🗺️ Spatial Intelligence", "📋 Data Berita"]
if is_admin:
    tab_labels.append("⚠️ Admin")

tabs = st.tabs(tab_labels)
tab_overview = tabs[0]
tab_spatial = tabs[1]
tab_data = tabs[2]
tab_admin = tabs[3] if is_admin else None

# ==================== TAB 1: OVERVIEW ====================
with tab_overview:
    if filtered_df.empty:
        st.info("💡 Tidak ada data yang sesuai dengan kriteria filter Anda.")
    else:
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("📰 Total Berita Terfilter", f"{len(filtered_df):,}")
        kpi2.metric("🏢 Portal Media Unik", f"{filtered_df[col_media].nunique() if col_media in filtered_df.columns else 0:,}")
        kpi3.metric("🔖 Keyword Aktif", f"{filtered_df[col_keyword].nunique() if col_keyword in filtered_df.columns else 0:,}")

        st.divider()
        st.markdown("### 📊 Grafik Analitik")

        def _sentiment_color_map(series):
            palette = {}
            for val in series.dropna().unique():
                v = str(val).strip().lower()
                if v.startswith("pos"):
                    palette[val] = "#10b981"
                elif v.startswith("neg"):
                    palette[val] = "#ef4444"
                else:
                    palette[val] = "#64748b"
            return palette

        _dark_chart_layout = dict(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#1a2233",
            title_font_color="#1a2233",
            margin=dict(t=40, b=20, l=20, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            if col_sentiment and col_sentiment in filtered_df.columns:
                fig_pie = px.pie(
                    filtered_df, names=col_sentiment, title="Distribusi Sentimen", hole=0.5,
                    color=col_sentiment, color_discrete_map=_sentiment_color_map(filtered_df[col_sentiment]),
                )
                fig_pie.update_layout(**_dark_chart_layout)
                st.plotly_chart(fig_pie, width='stretch')

        with col_chart2:
            if col_media in filtered_df.columns:
                top_media_chart = filtered_df[col_media].value_counts().reset_index()
                top_media_chart.columns = ['Media', 'Jumlah']
                fig_bar = px.bar(
                    top_media_chart.head(8), x='Media', y='Jumlah', title="Top Portal Media",
                    color='Jumlah', color_continuous_scale=["#bcd6f2", "#2563eb"],
                )
                fig_bar.update_layout(**_dark_chart_layout)
                st.plotly_chart(fig_bar, width='stretch')

# ==================== TAB SPATIAL: SPATIAL INTELLIGENCE ====================
with tab_spatial:
    st.markdown("### 🗺️ Spatial Intelligence: Peta Sebaran & Hotspot Liputan")
    st.caption(
        "Lokasi dideteksi dari nama kota/provinsi yang disebut di judul & isi berita "
        "(bukan geocoding presisi peristiwa). Berita yang menyebut beberapa kota "
        "dihitung untuk setiap kota yang disebut."
    )

    if filtered_df.empty:
        st.info("💡 Tidak ada data yang sesuai dengan kriteria filter Anda.")
    else:
        from app.services.geo_service import build_location_hotspots

        with st.spinner("Mendeteksi lokasi dari teks berita..."):
            hotspots_df = build_location_hotspots(
                filtered_df,
                title_col=col_title,
                content_col=col_content,
                sentiment_col=col_sentiment,
            )

        if hotspots_df.empty:
            st.info(
                "Tidak ada nama kota/provinsi Indonesia yang terdeteksi pada berita "
                "yang lolos filter saat ini."
            )
        else:
            spatial_kpi1, spatial_kpi2, spatial_kpi3 = st.columns(3)
            spatial_kpi1.metric("📍 Lokasi Terdeteksi", f"{len(hotspots_df):,}")
            spatial_kpi2.metric("🔥 Hotspot Teratas", hotspots_df.iloc[0]["location"])
            spatial_kpi3.metric("📰 Total Sebutan Lokasi", f"{int(hotspots_df['mention_count'].sum()):,}")

            def _sentiment_marker_color(val):
                v = str(val).strip().lower() if val else ""
                if v.startswith("pos"):
                    return "#10b981"
                if v.startswith("neg"):
                    return "#ef4444"
                return "#2563eb"

            hotspots_df["marker_color"] = hotspots_df["dominant_sentiment"].apply(_sentiment_marker_color)

            fig_map = px.scatter_geo(
                hotspots_df,
                lat="lat", lon="lon",
                size="mention_count",
                hover_name="location",
                hover_data={"mention_count": True, "dominant_sentiment": True, "lat": False, "lon": False},
                color="dominant_sentiment",
                color_discrete_map={"Positive": "#10b981", "Negative": "#ef4444", "Neutral": "#64748b",
                                     "POSITIVE": "#10b981", "NEGATIVE": "#ef4444", "NEUTRAL": "#64748b"},
                projection="natural earth",
                title="Sebaran Hotspot Berita di Indonesia",
            )
            fig_map.update_geos(
                center=dict(lat=-2.5, lon=118),
                projection_scale=4.2,
                showcountries=True, countrycolor="#c7ccd6",
                showland=True, landcolor="#e9edf3",
                showocean=True, oceancolor="#f6f8fb",
                bgcolor="rgba(0,0,0,0)",
            )
            fig_map.update_layout(
                template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                font_color="#1a2233", title_font_color="#1a2233",
                margin=dict(t=40, b=10, l=10, r=10), height=520,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_map, width='stretch')

            st.markdown("#### 🏆 Ranking Hotspot")
            st.dataframe(
                hotspots_df[["location", "mention_count", "dominant_sentiment"]].rename(columns={
                    "location": "Lokasi", "mention_count": "Jumlah Sebutan", "dominant_sentiment": "Sentimen Dominan"
                }),
                width='stretch', hide_index=True,
            )

# ==================== TAB 2: DATA BERITA ====================
with tab_data:
    st.markdown("### 📋 Daftar Berita Tersimpan")

    @st.dialog("Detail Berita", width="large")
    def show_news_detail(row):
        st.subheader(row[col_title])
        st.caption(f"📅 {row[date_col]} | 📰 {row[col_media]} | 🏷️ {row[col_sentiment]}")
        st.markdown("---")
        st.write(row[col_content])
        if st.button("Tutup"):
            st.rerun()

    event = st.dataframe(filtered_df, width='stretch', selection_mode="single-row", on_select="rerun", key="data_editor")

    if is_admin:
        selection = st.session_state.get("data_editor", None)
        if selection and "selection" in selection and len(selection["selection"]["rows"]) > 0:
            idx = selection["selection"]["rows"][0]
            show_news_detail(filtered_df.iloc[idx])
    else:
        if st.session_state.get("data_editor", {}).get("selection", {}).get("rows"):
            st.info("Fitur detail berita hanya tersedia untuk akun Admin.")

# ==================== TAB 3: ADMIN ====================
if is_admin:
    with tab_admin:
        st.warning("⚠️ Tindakan di tab ini bersifat permanen dan tidak dapat dibatalkan[cite: 16].")
        target_date = st.date_input("Pilih Tanggal Target Penghapusan", key="date_hapus_massal")
        admin_password = st.text_input("PostgreSQL Admin Password", type="password", key="pg_admin_password")

        if st.button("🚨 Eksekusi Hapus Masal Tanggal Ini", type="primary", width='stretch'):
            try:
                deleted = api_bridge.delete_articles_by_date(
                    target_date.strftime("%Y-%m-%d"), admin_password
                )
                st.success(f"Berhasil menghapus {deleted} artikel pada tanggal {target_date}.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menghapus: {e}")