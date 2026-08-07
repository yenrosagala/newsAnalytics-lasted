# app/utils/helpers.py
import streamlit as st
import os

def load_css(file_path: str = "app/assets/style.css"):
    """Inject external CSS file ke aplikasi Streamlit."""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"CSS file not found at {file_path}")