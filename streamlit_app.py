import streamlit as st
import os

# Konfigurasi Halaman Utama
st.set_page_config(
    page_title="News Intelligence & Analytics Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Memuat custom CSS jika tersedia
css_path = os.path.join("app", "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def get_latest_brief_from_backend():
    return {
        "keyword": "kekeringan di NTT",
        "created_at": "2026-08-06 23:24:19",
        "situation": "Badan Meteorologi (BMGK) mengingatkan ancaman kekeringan ekstrem di hampir seluruh wilayah Nusa Tenggara Timur (NTT) akibat El Niño, dengan 14 kabupaten mengalami hari tanpa hujan (HTH) lebih dari 60 hari.",
        "risks": [
            {"label": "Gagal Panen (Tinggi)", "color": "#fee2e2", "text_color": "#991b1b"},
            {"label": "Kekurangan Air Bersih (Sedang)", "color": "#fef3c7", "text_color": "#92400e"}
        ]
    }

def main():
    st.title("📊 News Intelligence & Analytics Dashboard")
    st.markdown("Platform intelijen berita terintegrasi untuk pemantauan krisis, tren prediktif, dan analisis mendalam secara real-time.")

    st.markdown("---")
    
    # ==========================================
    # 1. DECISION BRIEF DINAMIS (HOOK UTAMA)
    # ==========================================
    st.markdown("### 📋 Brief Terbaru (Executive Summary)")
    
    latest_brief = get_latest_brief_from_backend()
    
    risk_badges = "".join([
        f'<span style="background-color: {r["color"]}; color: {r["text_color"]}; padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">{r["label"]}</span>'
        for r in latest_brief["risks"]
    ])
    
    st.markdown(f"""
    <div style="background-color: #ffffff; border-left: 5px solid #2563eb; border: 1px solid #e2e8f0; padding: 1.5rem; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 1.5rem;">
        <p style="font-size: 0.8rem; color: #64748b; margin-bottom: 0.5rem;">Kata kunci: <b>{latest_brief['keyword']}</b> • Dibuat: {latest_brief['created_at']}</p>
        <h4 style="color: #1e293b; margin-top: 0; font-size: 1.15rem;">Situation & Critical Alert</h4>
        <p style="color: #334155; font-size: 0.95rem; line-height: 1.5; margin-bottom: 1rem;">
            {latest_brief['situation']}
        </p>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            {risk_badges}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Tombol aksi brief disatukan dalam baris rapi
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🔍 Investigasi Brief Ini", use_container_width=True, key="brief_investigasi"):
            try:
                st.switch_page("pages/1_Scraping.py")
            except Exception:
                st.info("Silakan akses halaman AI Investigator melalui sidebar.")
    with col_b2:
        if st.button("➕ Buat Brief Baru", use_container_width=True, key="brief_buat_baru"):
            st.success("Form pembuatan brief baru diaktifkan.")

    st.markdown("---")

    # ==========================================
    # 2. JELAJAHI MODUL (KARTU TERPADU SATU KESATUAN)
    # ==========================================
    st.markdown("### Jelajahi Modul Analitik")
    
    features = [
        {"title": "AI Investigator", "desc": "Telusuri akar masalah secara rekursif, lengkap dengan evidence graph & skor keyakinan.", "page": "pages/1_Scraping.py"},
        {"title": "Predictive Intelligence", "desc": "Deteksi tren naik/turun dan peringatan otomatis saat terjadi lonjakan tak wajar.", "page": "pages/4_Predictive_Intelligence.py"},
        {"title": "News Intelligence", "desc": "Ambil data berita terkini dan kelola ringkasan eksekutif tersimpan.", "page": "pages/3_Fenomena.py"},
        {"title": "News Analytics", "desc": "Visualisasi data mentah yang terkumpul, lengkap dengan filter dan panel admin.", "page": "pages/2_Dashboard.py"},
        {"title": "Social Media Intelligence", "desc": "Ambil konten publik dari Facebook, Instagram, YouTube, Threads, dan X/Twitter.", "page": "pages/5_Social_Media_Scraper.py"}
    ]
    
    # Menggunakan grid 3 kolom
    cols = st.columns(3)
    
    for idx, feat in enumerate(features):
        col_idx = idx % 3
        with cols[col_idx]:
            # Menggunakan satu kontainer visual murni yang merangkap teks & tombol secara kompak
            st.markdown(f"""
                <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 1.5rem; border-radius: 12px; height: 180px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 1px 3px rgba(0,0,0,0.02); margin-bottom: 1rem;">
                    <div>
                        <h4 style="color: #1e293b; margin-top: 0; font-size: 1.05rem; font-weight: 600; margin-bottom: 0.5rem;">{feat['title']}</h4>
                        <p style="color: #64748b; font-size: 0.8rem; line-height: 1.4; margin: 0;">{feat['desc']}</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Tombol diletakkan tepat di bawah teks dalam satu blok kolom card
            if st.button(f"Buka Modul &rarr;", key=f"feat_btn_{idx}", use_container_width=True):
                try:
                    st.switch_page(feat['page'])
                except Exception:
                    st.info(f"Buka halaman {feat['title']} dari menu navigasi sidebar.")

if __name__ == "__main__":
    main()