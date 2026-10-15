import os
import streamlit as st


def _get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


class Config:
    # --------------------------------------------------------------
    # KREDENSIAL LOGIN ADMIN
    # Aplikasi ini terbuka bebas untuk pengguna umum (tidak perlu login).
    # Login HANYA dipakai untuk mengakses fitur manajemen database (admin).
    # HANYA dibaca dari st.secrets (atau env var sebagai fallback untuk
    # dev lokal non-Streamlit). TIDAK ADA default password tertanam di
    # kode -- jika secret ini kosong, login admin dinonaktifkan
    # (fail-closed), bukan diam-diam pakai password lemah yang sudah
    # terpublikasi di GitHub.
    # --------------------------------------------------------------
    ADMIN_USERNAME = _get_secret("ADMIN_USERNAME", os.getenv("ADMIN_USERNAME", "admin"))
    ADMIN_PASSWORD = _get_secret("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
