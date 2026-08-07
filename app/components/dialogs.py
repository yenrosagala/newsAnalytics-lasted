import streamlit as st

@st.dialog("Konfirmasi Aksi")
def confirm_action(action_name: str):
    """Dialog konfirmasi sebelum melakukan aksi fatal."""
    st.warning(f"Apakah Anda yakin ingin melakukan {action_name}?")
    if st.button("Ya, Lanjutkan"):
        st.session_state["confirmed"] = True
        st.rerun()