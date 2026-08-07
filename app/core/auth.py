import streamlit as st
from app.core.config import Config


def init_auth_session():
    """Inisialisasi variabel session login saat aplikasi pertama kali dimuat."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.username = ""


def is_authenticated() -> bool:
    """Mengecek status login ADMIN.

    st.session_state bersifat per-browser-session dan dibagikan ke SEMUA
    halaman pada aplikasi multipage Streamlit ini -- jadi begitu status ini
    True, ia tetap True saat pengguna berpindah halaman (Scraping/Dashboard/
    Fenomena) TANPA perlu login ulang, selama tab browser yang sama tidak
    ditutup/refresh penuh.
    """
    return bool(st.session_state.get("authenticated", False))


def is_admin() -> bool:
    """True hanya jika pengguna sudah login SEBAGAI ADMIN."""
    return is_authenticated() and st.session_state.get("role") == "admin"


def require_login():
    """Dipanggil di baris paling atas fitur yang WAJIB admin (mis. hapus data).

    Aplikasi ini tidak lagi mewajibkan login untuk pengguna umum -- fungsi ini
    hanya dipakai untuk menggerbang fitur spesifik yang berhubungan dengan
    manajemen database, bukan seluruh halaman.
    """
    if not is_admin():
        st.warning("⚠️ Fitur ini khusus Admin. Silakan login lewat panel di sidebar terlebih dahulu.")
        st.stop()


def render_login_form():
    """Form login admin. Dipakai di dalam render_auth_sidebar()."""
    if not Config.ADMIN_PASSWORD:
        st.error(
            "⚠️ ADMIN_PASSWORD belum dikonfigurasi di st.secrets. Login admin "
            "dinonaktifkan sampai secret ini diisi -- lihat Settings > Secrets."
        )
        return

    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")

    if st.button("Login", key="btn_login_admin"):
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.session_state.role = "admin"
            st.session_state.username = username
            st.success("Login Admin berhasil!")
            st.rerun()
        else:
            st.error("Username atau password salah!")


def render_logout():
    """Tombol logout untuk membersihkan session state."""
    if st.button("Logout", key="btn_logout_admin"):
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.username = ""
        st.rerun()


def render_auth_sidebar():
    """Widget status login ringkas untuk sidebar, dipanggil di SETIAP halaman.

    Aplikasi ini terbuka bebas untuk pengguna umum -- tidak perlu login sama
    sekali untuk scraping, melihat dashboard, atau menjalankan analisis 5-Why.
    Login hanya dibutuhkan agar admin bisa mengakses fitur manajemen database
    (mis. hapus data di halaman Dashboard). Widget ini memastikan admin bisa
    login dari halaman mana pun, tidak harus kembali ke Homepage dulu.
    """
    init_auth_session()
    with st.sidebar:
        st.markdown("---")
        if is_admin():
            st.success(f"Masuk sebagai: **Admin** ({st.session_state.get('username', '')})")
            render_logout()
        else:
            st.caption(
                "🔓 Anda menjelajah sebagai pengguna umum -- semua fitur "
                "scraping, dashboard, dan analisis 5-Why dapat langsung "
                "dipakai tanpa login."
            )
            with st.expander("🔒 Login Admin (khusus manajemen database)"):
                render_login_form()