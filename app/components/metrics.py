import streamlit as st
import pandas as pd

def render_kpi(df: pd.DataFrame) -> None:
    """Menampilkan KPI utama dashboard."""
    col_media = "source" if "source" in df.columns else "media"
    col_keyword = "keyword" if "keyword" in df.columns else "kata_kunci"
    
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Berita Terfilter", len(df))
    kpi2.metric("Portal Media Unik", df[col_media].nunique())
    kpi3.metric("Keyword Aktif", df[col_keyword].nunique())

def render_metric_card(label, value, delta=None, status="normal"):
    """
    Merender kartu metrik yang bersih dengan indikator status/delta visual.
    """
    delta_html = ""
    if delta:
        color = "#10b981" if "+" in str(delta) else "#ef4444"
        delta_html = f"<span style='color: {color}; font-size: 0.85rem; font-weight: 600;'>{delta}</span>"
    
    st.markdown(f"""
        <div style="background-color: #ffffff; border: 1px solid #e2e8f0; padding: 1.25rem; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <p style="color: #64748b; font-size: 0.875rem; margin-bottom: 0.5rem; font-weight: 500;">{label}</p>
            <div style="display: flex; align-items: baseline; justify-content: space-between;">
                <h3 style="color: #0f172a; font-size: 1.75rem; font-weight: 700; margin: 0;">{value}</h3>
                {delta_html}
            </div>
        </div>
    """, unsafe_allow_html=True)