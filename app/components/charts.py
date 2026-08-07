import streamlit as st
import pandas as pd
import plotly.express as px

def render_charts(df: pd.DataFrame) -> None:
    """Menampilkan grafik analisis sentimen dan tren."""
    if df.empty:
        st.info("Data tidak tersedia untuk visualisasi.")
        return

    st.subheader("Visualisasi Data")
    
    # Contoh chart: Distribusi Sentimen
    fig = px.pie(df, names="Sentimen", title="Distribusi Sentimen Berita")
    st.plotly_chart(fig, width='stretch')

    # Contoh chart: Tren Berita per Media
    fig_bar = px.bar(df, x="media", title="Jumlah Berita per Media")
    st.plotly_chart(fig_bar, width='stretch')