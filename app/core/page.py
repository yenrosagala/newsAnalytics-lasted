"""Bootstrap halaman Streamlit: set_page_config + CSS + sidebar nav + auth.

Dibuat karena kelima halaman mengulang urutan 4 baris yang sama. Ditaruh di
modul sendiri (bukan app/components/sidebar.py) supaya tetap menghormati
pemisahan yang sudah didokumentasikan di sidebar.py: auth sengaja TIDAK
digabung ke sidebar, jadi yang menggabungkan keduanya adalah halaman, bukan
salah satu komponennya.
"""
import streamlit as st

from app.core.auth import render_auth_sidebar
from app.components.sidebar import load_custom_css, render_app_sidebar


def setup_page(page_title: str, page_icon: str, active_page: str) -> None:
    st.set_page_config(page_title=page_title, layout="wide", page_icon=page_icon)
    load_custom_css()
    render_app_sidebar(active_page=active_page)
    render_auth_sidebar()
