"""Renderer Ringkasan Berita (news summary) -- esai naratif untuk halaman
Scraping berita dan Social Media Scraper. Berbeda dari
decision_brief_view.render_decision_brief yang menampilkan Executive
Intelligence Brief S-R-I-R (halaman AI Investigator / Fenomena)."""
import streamlit as st


def render_news_summary(summary: dict) -> None:
    if not summary or not (summary.get("title") or summary.get("summary")):
        st.info("Belum ada ringkasan berita untuk ditampilkan.")
        return

    if summary.get("title"):
        st.markdown(f"### {summary['title']}")
    if summary.get("summary"):
        st.markdown(summary["summary"])
