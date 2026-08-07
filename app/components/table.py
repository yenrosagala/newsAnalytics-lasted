import streamlit as st
import pandas as pd

def render_data_table(df: pd.DataFrame) -> None:
    """Menampilkan data dalam bentuk tabel interaktif."""
    st.subheader("Data Artikel")
    st.dataframe(
        df,
        column_config={
            "waktu_tampilan": st.column_config.DateColumn("Tanggal"),
            "judul": st.column_config.TextColumn("Judul Berita", width="large")
        },
        width='stretch'
    )