import streamlit as st

def init_session_state(key: str, default_value):
    """Menginisialisasi session state jika belum ada."""
    if key not in st.session_state:
        st.session_state[key] = default_value

def get_session_state(key: str, default_value=None):
    """Mengambil nilai session state dengan aman."""
    init_session_state(key, default_value)
    return st.session_state[key]

def set_session_state(key: str, value):
    """Mengubah nilai session state."""
    st.session_state[key] = value

# --- ALIAS UNTUK KOMPATIBILITAS KODE BARU ---
def init_state(key: str, default_value):
    return init_session_state(key, default_value)

def get_state(key: str, default_value=None):
    return get_session_state(key, default_value)

def set_state(key: str, value):
    return set_session_state(key, value)