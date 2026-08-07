import streamlit as st

def init_dashboard_state():
    """Inisialisasi state aplikasi secara terpusat."""
    defaults = {
        "authenticated": False,
        "role": "user",
        "gemini_dashboard_summary": "",
        "active_keyword": [],
        "current_keyword": ""
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value