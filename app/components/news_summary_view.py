"""Renderer Ringkasan Berita (news summary) -- esai naratif untuk halaman
Scraping berita dan Social Media Scraper. Berbeda dari
decision_brief_view.render_decision_brief yang menampilkan Executive
Intelligence Brief S-R-I-R (halaman AI Investigator / Fenomena)."""
import streamlit as st


def _citation_map(bibliography: list) -> dict:
    return {b["n"]: b.get("url") for b in bibliography if b.get("n") and b.get("url")}


def _format_entry(entry: dict) -> str:
    label = f"[{entry.get('n')}] {entry.get('media') or '-'} — {entry.get('title') or '-'}"
    if entry.get("date"):
        label += f" ({entry['date']})"
    if entry.get("url"):
        label += f" — {entry['url']}"
    return label


def render_news_summary(summary: dict) -> None:
    if not summary or not (summary.get("title") or summary.get("summary")):
        st.info("Belum ada ringkasan berita untuk ditampilkan.")
        return

    bibliography = summary.get("bibliography") or []

    if summary.get("title"):
        st.markdown(f"### {summary['title']}")
    if summary.get("summary"):
        body = summary["summary"]
        if bibliography:
            # Sitasi [n] di esai di-linkify ke URL sumber asli. Reuse helper
            # chatbot (import lokal: chatbot memuat ai_service, tidak perlu
            # ikut ter-load saat modul ini diimpor).
            from app.components.chatbot import _linkify_citations
            body = _linkify_citations(body, _citation_map(bibliography))
        st.markdown(body)

    if bibliography:
        with st.expander(f"📚 Daftar Pustaka ({len(bibliography)} sumber)"):
            for entry in bibliography:
                st.markdown(_format_entry(entry))
