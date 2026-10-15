import re

import streamlit as st

from app.components.decision_brief_view import render_decision_brief
from app.core.page import setup_page
from app import api_bridge

setup_page("Home", "🏠", "streamlit_app.py")


@st.cache_data(ttl=60)
def get_latest_brief():
    """Brief Executive terbaru dari tabel executive_summaries (di-cache 60 detik
    supaya tiap klik widget di halaman Home tidak memanggil Supabase ulang)."""
    return api_bridge.get_latest_brief()


def main():
    st.title("📊 News Intelligence & Analytics Dashboard")
    st.markdown(
        "Platform intelijen berita terintegrasi untuk pemantauan krisis, "
        "tren prediktif, dan analisis mendalam secara real-time."
    )

    # Animasi JARVIS (arc reactor) -- murni CSS, jalankan di browser tanpa JS.
    st.markdown(
        """
        <div class="jarvis-reactor" title="JARVIS online">
            <div class="jr-ring--outer"></div>
            <div class="jr-ring--mid"></div>
            <div class="jr-ring--inner"></div>
            <div class="jr-core"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ==========================================
    # 1. BRIEF TERBARU (DARI DATABASE, BUKAN DATA CONTOH)
    # ==========================================
    st.markdown("### 📋 Brief Terbaru (Executive Summary)")
    keyword, brief, created_at, brief_error = get_latest_brief()

    if brief_error:
        st.error(f"⚠️ Gagal memuat brief terbaru dari database: {brief_error}")
    elif not brief:
        st.info(
            "Belum ada Executive Brief tersimpan. Jalankan **News Scraper** untuk "
            "mengumpulkan berita dan membangun ringkasan pertama Anda."
        )
        if st.button("📥 Mulai dari News Scraper", type="primary", width='stretch', key="brief_kosong_scraper"):
            st.switch_page("pages/1_Scraping.py")
    else:
        st.caption(f"Kata kunci: **{keyword or '-'}**  •  Dibuat: {created_at or '-'}")

        # Tampilkan hanya paragraf ringkasan (Situation) sebagai summary singkat.
        # Penanda sitasi [1] dibuang supaya kalimatnya mengalir tanpa noise.
        # Brief lengkap tetap bisa dibuka lewat expander di bawah.
        situation = brief.get("situation") if isinstance(brief, dict) else brief
        if situation:
            st.markdown(re.sub(r"\s*\[\d+\]", "", str(situation)).strip())
        else:
            st.markdown("_Ringkasan singkat belum tersedia untuk brief ini._")

        with st.expander("📄 Lihat brief lengkap (Situation / Risks / Impact / Recommendations)"):
            render_decision_brief(brief)

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("🔍 Investigasi Fenomena Ini", width='stretch', key="brief_investigasi"):
                if keyword:
                    st.session_state["last_recursive_query"] = keyword
                st.switch_page("pages/3_Fenomena.py")
        with col_b2:
            if st.button("📥 Kumpulkan Berita Baru", width='stretch', key="brief_kumpulkan"):
                if keyword:
                    st.session_state["current_keyword"] = keyword
                st.switch_page("pages/1_Scraping.py")

    st.markdown("---")

    # ==========================================
    # 2. JELAJAHI MODUL (KARTU TERPADU SATU KESATUAN)
    # ==========================================
    st.markdown("### Jelajahi Modul Analitik")

    # Label & tujuan halaman harus persis sama dengan NAV_ITEMS di
    # app/components/sidebar.py supaya nama modul konsisten di semua tempat.
    features = [
        {"title": "AI Investigator", "desc": "Telusuri akar masalah secara rekursif, lengkap dengan evidence graph & skor keyakinan.", "page": "pages/3_Fenomena.py"},
        {"title": "Predictive Intelligence", "desc": "Deteksi tren naik/turun dan peringatan otomatis saat terjadi lonjakan tak wajar.", "page": "pages/4_Predictive_Intelligence.py"},
        {"title": "News Scraper", "desc": "Ambil data berita terkini dan kelola ringkasan eksekutif tersimpan.", "page": "pages/1_Scraping.py"},
        {"title": "Analytics Dashboard", "desc": "Visualisasi data mentah yang terkumpul, lengkap dengan filter dan panel admin.", "page": "pages/2_Dashboard.py"},
        {"title": "Social Media Scraper", "desc": "Ambil konten publik dari Facebook, Instagram, YouTube, Threads, dan X/Twitter.", "page": "pages/5_Social_Media_Scraper.py"},
    ]

    cols = st.columns(3)

    for idx, feat in enumerate(features):
        with cols[idx % 3]:
            st.markdown(f"""
                <div style="background: rgba(10,24,43,0.62); border: 1px solid rgba(56,189,248,0.24); padding: 1.5rem; border-radius: 12px; height: 180px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 8px 32px rgba(0,0,0,0.30); margin-bottom: 1rem;">
                    <div>
                        <h4 style="color: #dff3ff; margin-top: 0; font-size: 1.05rem; font-weight: 600; margin-bottom: 0.5rem;">{feat['title']}</h4>
                        <p style="color: #7fa8c9; font-size: 0.8rem; line-height: 1.4; margin: 0;">{feat['desc']}</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            if st.button("Buka Modul →", key=f"feat_btn_{idx}", width='stretch'):
                st.switch_page(feat['page'])


if __name__ == "__main__":
    main()
