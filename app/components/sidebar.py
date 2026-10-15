"""
Shared app chrome: custom CSS loading + sidebar navigation.

Sebelumnya, blok ini (load CSS + 4 st.page_link + caption info) di-copy-paste
persis sama di tiap halaman -- kalau menu berubah (nama, ikon, urutan), harus
diedit di banyak tempat sekaligus dan gampang lupa satu. Sekarang jadi SATU
sumber kebenaran di sini.

Catatan: widget status login (render_auth_sidebar di app/core/auth.py)
sengaja TETAP terpisah dari file ini -- itu murni tentang autentikasi,
sedangkan file ini murni tentang navigasi & tampilan, dua concern yang
berbeda meskipun sama-sama muncul di sidebar. Yang menggabungkan keduanya
(CSS + nav + auth) adalah app/core/page.py::setup_page, dipanggil tiap
halaman dengan satu baris:

    setup_page("Analytics", "📊", "pages/2_Dashboard.py")
"""
import os

import streamlit as st

from app.services.database_service import db_service
from app.services.ai_service import ai_service
from app.components.voice_input import render_jarvis_voice_bar


def resolve_project_path(path: str) -> str:
    """Return a path string that exists from the current working directory.

    Streamlit page links are resolved relative to the entrypoint directory, which
    can be the project root or its parent depending on how the app is launched.
    This helper tries both layouts so the sidebar and page switches keep working.
    """
    cwd = os.getcwd()
    candidates = [path, os.path.join("newsAnalytics-main", path)]
    for candidate in candidates:
        if os.path.exists(os.path.join(cwd, candidate)):
            return candidate

    parent_dir = os.path.dirname(cwd)
    for candidate in candidates:
        if os.path.exists(os.path.join(parent_dir, candidate)):
            return candidate

    return path


# Satu-satunya tempat daftar menu navigasi didefinisikan. Tambah/ubah/hapus
# menu cukup di sini, otomatis konsisten di semua halaman.
#
# Dikelompokkan mengikuti perjalanan keputusan pengguna, bukan sekadar
# kapabilitas teknis (scrape/analisis/prediksi):
#   Briefs      -- "apa yang perlu saya tahu" (Home, nanti berisi brief terbaru)
#   Investigate -- "kenapa ini terjadi" (drill-down: root cause, tren/anomali)
#   Sources     -- "data mentah di baliknya" (koleksi & eksplorasi data)
# render_app_sidebar() mencetak header section baru setiap kali nilai
# "section" berubah, sehingga sidebar sendiri mengajarkan alur: lihat brief
# dulu -> investigasi kalau perlu -> baru masuk ke sumber data mentah.
NAV_ITEMS = [
    {"page": "streamlit_app.py", "label": "Home", "icon": "🏠", "section": "Briefs"},
    {"page": "pages/3_Fenomena.py", "label": "AI Investigator", "icon": "🕵️", "section": "Investigate"},
    {"page": "pages/4_Predictive_Intelligence.py", "label": "Predictive Intelligence", "icon": "🔮", "section": "Investigate"},
    {"page": "pages/1_Scraping.py", "label": "News Scraper", "icon": "📥", "section": "Sources"},
    {"page": "pages/2_Dashboard.py", "label": "Analytics Dashboard", "icon": "📊", "section": "Sources"},
    {"page": "pages/5_Social_Media_Scraper.py", "label": "Social Media Scraper", "icon": "🌐", "section": "Sources"},
]

# Caption default "Informasi" per halaman -- override lewat parameter
# info_caption di render_app_sidebar() kalau suatu halaman butuh teks lain.
DEFAULT_INFO_CAPTIONS = {
    "streamlit_app.py": "AI Decision Intelligence Platform -- ubah berita jadi intelijen yang actionable.",
    "pages/1_Scraping.py": "Fitur mengeksplorasi berita dan memberikan insight secara menyeluruh.",
    "pages/2_Dashboard.py": "Visualisasi data berita terkumpul, lengkap dengan filter dan panel admin.",
    "pages/3_Fenomena.py": (
        "AI Investigator menelusuri berita secara berlapis (Recursive 5-Why) untuk "
        "mengidentifikasi akar permasalahan, lengkap dengan evidence graph & skor keyakinan."
    ),
    "pages/4_Predictive_Intelligence.py": (
        "Predictive Intelligence mendeteksi tren naik/turun, memproyeksikan volume berita "
        "ke depan, dan memberi peringatan otomatis saat terjadi lonjakan/penurunan tak wajar."
    ),
    "pages/5_Social_Media_Scraper.py": (
        "Social Media Scraper mengambil konten publik dari Facebook, Instagram, YouTube, "
        "Threads, dan X/Twitter via Selenium -- tanpa login otomatis, hanya data publik."
    ),
}


def load_custom_css(css_path: str = "app/assets/style.css") -> None:
    """Muat file CSS kustom aplikasi. Dipanggil sekali di awal tiap page script."""
    resolved_css = resolve_project_path(css_path)
    if os.path.exists(os.path.join(os.getcwd(), resolved_css)):
        with open(os.path.join(os.getcwd(), resolved_css)) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=30, show_spinner=False)
def _get_system_status() -> dict:
    """Cek status DB & AI provider, di-cache 30 detik supaya tidak membebani
    Supabase/Ollama setiap kali Streamlit rerun (mis. tiap klik widget)."""
    return {
        "db": db_service.check_status(),
        "ai": ai_service.check_status(),
    }


def render_status_bar() -> None:
    """Bar status sistem yang tampil di SETIAP halaman (bukan cuma Home) --
    supaya kalau Supabase/AI provider bermasalah, pengguna langsung tahu di
    mana pun mereka berada, bukan menebak-nebak dari gejala tak langsung
    (mis. dashboard kosong, investigasi gagal tanpa alasan jelas)."""
    status = _get_system_status()
    db_ok = status["db"]["ok"]
    ai_ok = status["ai"]["ok"]

    db_dot = "🟢" if db_ok else "🔴"
    ai_dot = "🟢" if ai_ok else "🔴"

    st.markdown(
        f"""
        <div class="d-status-bar">
            <div class="d-status-pill" title="{status['db']['detail']}">
                {db_dot} <span>Database</span>
            </div>
            <div class="d-status-pill" title="{status['ai']['detail']}">
                {ai_dot} <span>AI &middot; {status['ai']['provider']}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not db_ok:
        st.caption(f"⚠️ Database: {status['db']['detail']}")
    if not ai_ok:
        st.caption(f"⚠️ AI: {status['ai']['detail']}")


def render_app_sidebar(active_page: str, info_caption: str | None = None) -> None:
    """Render blok navigasi sidebar yang identik di semua halaman.

    Markup mengikuti struktur Adminator (brand block + nav section berlabel
    + footer info), lihat github.com/puikinsh/Adminator-admin-dashboard.

    active_page: path relatif halaman saat ini persis seperti didaftarkan
        di NAV_ITEMS (mis. "pages/1_Scraping.py"), dipakai untuk memilih
        caption info default yang sesuai.
    info_caption: teks kustom untuk bagian "Informasi", override caption
        default kalau diisi.
    """
    with st.sidebar:
        st.markdown(
            """
            <div class="d-brand">
                <div class="d-brand-logo">⚡</div>
                <div class="d-brand-text">
                    <div class="d-brand-name">NewsAnalytics AI</div>
                    <div class="d-brand-tag">DECISION INTELLIGENCE</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        current_section = "__unset__"  # sentinel != None, biar section None (Home) tetap dianggap "beda"
        for item in NAV_ITEMS:
            section = item.get("section")
            if section != current_section:
                st.markdown(
                    f'<div class="d-nav-label">{section or "Menu"}</div>', unsafe_allow_html=True
                )
                current_section = section
            st.page_link(resolve_project_path(item["page"]), label=item["label"], icon=item["icon"])

        render_jarvis_voice_bar()
        render_status_bar()

        st.markdown('<div class="d-sidebar-footer">', unsafe_allow_html=True)
        st.markdown('<div class="d-nav-label">Informasi</div>', unsafe_allow_html=True)
        st.caption(info_caption or DEFAULT_INFO_CAPTIONS.get(active_page, ""))
        st.markdown("</div>", unsafe_allow_html=True)