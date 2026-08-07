"""
Ringkasan cepat (non-AI) hasil Social Media Scraper.

Berbeda dari executive_summary_service (yang memanggil AI dan perlu waktu),
komponen ini murni statistik deskriptif dari post yang BARU SAJA diambil --
distribusi platform, kontributor teratas, dan snapshot topik dari kata yang
paling sering muncul -- sehingga pengguna langsung dapat gambaran begitu
scraping selesai, tanpa menunggu AI atau membuka file PDF.

Dipakai oleh pages/5_Social_Media_Scraper.py.
"""
import re
from collections import Counter
from typing import List, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

_STOPWORDS = {
    "yang", "dari", "dengan", "dan", "ke", "di", "pada", "untuk", "atau",
    "ini", "itu", "juga", "sebagai", "oleh", "karena", "saat", "adalah",
    "lebih", "dalam", "mereka", "tersebut", "akan", "tidak", "ada", "saya",
    "kami", "kita", "bisa", "sudah", "masih", "seperti", "hanya", "para",
    "the", "and", "for", "with", "this", "that", "you", "your", "are",
    "was", "have", "has", "not", "but", "from", "just", "will", "https",
}

_CHART_LAYOUT = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
    font_color="#1a2233", title_font_color="#1a2233",
    margin=dict(t=40, b=10, l=10, r=10), showlegend=False,
)


def _top_keywords(contents: pd.Series, max_keywords: int = 8) -> List[Tuple[str, int]]:
    """Hitung kata bermakna (>=4 huruf, bukan stopword) yang paling sering
    muncul di isi post -- pendekatan heuristik cepat sebagai pengganti
    topic-modeling AI, cukup untuk gambaran "sedang ramai membahas apa"."""
    counts = Counter()
    for text in contents.dropna():
        for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", str(text).lower()):
            if token in _STOPWORDS:
                continue
            counts[token] += 1
    return counts.most_common(max_keywords)


def render_social_summary(posts_df: pd.DataFrame) -> None:
    """Tampilkan ringkasan statistik (KPI + grafik + topik) dari hasil
    social media scraping yang baru dijalankan. Aman dipanggil dengan
    DataFrame kosong -- akan langsung return tanpa render apa pun."""
    if posts_df is None or posts_df.empty:
        return

    st.markdown("### 📊 Ringkasan Hasil Scraping")

    total_posts = len(posts_df)
    n_platforms = posts_df["platform"].nunique() if "platform" in posts_df.columns else 1
    n_authors = posts_df["author"].nunique() if "author" in posts_df.columns else 0
    if "content" in posts_df.columns and not posts_df["content"].dropna().empty:
        avg_len = int(posts_df["content"].dropna().astype(str).str.len().mean())
    else:
        avg_len = 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("📥 Total Post", f"{total_posts:,}")
    kpi2.metric("🌐 Platform Tercakup", f"{n_platforms}")
    kpi3.metric("👤 Akun/Author Unik", f"{n_authors:,}")
    kpi4.metric("📝 Rata-rata Panjang Konten", f"{avg_len} kar.")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        if "platform" in posts_df.columns and n_platforms > 1:
            platform_counts = posts_df["platform"].value_counts().reset_index()
            platform_counts.columns = ["Platform", "Jumlah"]
            fig = px.bar(
                platform_counts, x="Platform", y="Jumlah",
                title="Distribusi Post per Platform",
                color="Jumlah", color_continuous_scale=["#bcd6f2", "#2563eb"],
            )
            fig.update_layout(**_CHART_LAYOUT)
            st.plotly_chart(fig, width='stretch')
        elif "author" in posts_df.columns and n_authors > 0:
            top_authors = posts_df["author"].value_counts().head(8).reset_index()
            top_authors.columns = ["Akun", "Jumlah Post"]
            fig = px.bar(
                top_authors, x="Jumlah Post", y="Akun", orientation="h",
                title="Kontributor Teratas",
                color="Jumlah Post", color_continuous_scale=["#bcd6f2", "#2563eb"],
            )
            fig.update_layout(**_CHART_LAYOUT, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Belum cukup data untuk menampilkan grafik distribusi.")

    with col_right:
        st.markdown("##### 🔑 Topik yang Sering Muncul")
        keywords = _top_keywords(posts_df["content"]) if "content" in posts_df.columns else []
        if keywords:
            chips = "".join(
                f"<span style='display:inline-block; background:rgba(32,107,196,0.08); "
                f"color:#2563eb; border:1px solid rgba(32,107,196,0.25); border-radius:14px; "
                f"padding:3px 12px; margin:3px 4px 3px 0; font-size:0.82rem; font-weight:600;'>"
                f"{word} · {count}</span>"
                for word, count in keywords
            )
            st.markdown(chips, unsafe_allow_html=True)
        else:
            st.caption("Konten belum cukup untuk mengekstrak topik yang menonjol.")

    if n_platforms > 1 and "author" in posts_df.columns and n_authors > 0:
        with st.expander("👤 Lihat Kontributor Teratas (semua platform)"):
            top_authors_all = posts_df["author"].value_counts().head(10).reset_index()
            top_authors_all.columns = ["Akun", "Jumlah Post"]
            st.dataframe(top_authors_all, width='stretch', hide_index=True)
