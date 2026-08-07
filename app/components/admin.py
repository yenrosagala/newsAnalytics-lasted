import streamlit as st
from app.services.database_service import db_service

def render_admin_panel() -> None:
    """Panel khusus admin untuk manajemen data."""
    st.header("⚙️ Admin Panel")
    
    with st.expander("Manajemen Hapus Data (Massal)"):
        target_date = st.date_input("Pilih Tanggal")
        if st.button("Hapus Data Tanggal Ini", type="primary"):
            success = db_service.delete_articles_by_date(target_date.strftime("%Y-%m-%d"))
            if success:
                st.success("Data berhasil dihapus!")
                st.rerun()
            else:
                st.error("Gagal menghapus data.")