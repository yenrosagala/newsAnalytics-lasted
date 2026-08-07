import streamlit as st


def render_decision_brief(brief: dict, show_bibliography: bool = False) -> None:
    """Render satu Decision Intelligence Executive Brief (Situation / Risks /
    Impact / Recommendations) ke UI Streamlit dengan styling konsisten.

    Dipakai oleh AI Investigator (pages/3_Fenomena.py) dan oleh Social Media
    Scraper (pages/5_Social_Media_Scraper.py) untuk menampilkan ringkasan
    naratif AI langsung di halaman, sebelum PDF-nya diunduh.
    """
    # Import lokal (bukan di top-level modul) supaya file ini tidak pernah
    # ikut serta dalam rantai circular-import apa pun saat Python meng-import
    # app.services.decision_brief -- pada saat fungsi ini benar-benar
    # dipanggil, seluruh modul aplikasi sudah pasti selesai di-import.
    from app.services.decision_brief import SEVERITY_COLORS

    if not brief:
        st.info("Belum ada Executive Brief untuk ditampilkan.")
        return

    has_content = any([
        brief.get("situation"), brief.get("risks"),
        brief.get("impact"), brief.get("recommendations"),
    ])
    if not has_content:
        st.info("Belum ada Executive Brief untuk ditampilkan.")
        return

    if brief.get("situation"):
        st.markdown("#### 🎯 Situation")
        st.markdown(brief["situation"])
        st.markdown("")

    if brief.get("risks"):
        st.markdown("#### ⚠️ Risks")
        for r in brief["risks"]:
            color = SEVERITY_COLORS.get(r.get("severity", "Sedang"), "#64748b")
            badge = (
                f"<span style='background:{color}22; color:{color}; border:1px solid {color}66; "
                f"border-radius:6px; padding:1px 8px; font-size:0.72rem; font-weight:700; margin-left:6px;'>"
                f"{r.get('severity', 'Sedang')}</span>"
            )
            st.markdown(f"- {r.get('risk', '')} {badge}", unsafe_allow_html=True)
            if r.get("rationale"):
                st.markdown(
                    f"<p style='color:#64748b; font-size:0.82rem; margin:0 0 6px 16px;'>↳ {r['rationale']}</p>",
                    unsafe_allow_html=True,
                )
        st.markdown("")

    if brief.get("impact"):
        st.markdown("#### 📉 Impact")
        st.markdown(brief["impact"])
        st.markdown("")

    if brief.get("recommendations"):
        st.markdown("#### ✅ Recommendations")
        for rec in brief["recommendations"]:
            st.markdown(f"- {rec}")

    if show_bibliography and brief.get("bibliography"):
        with st.expander("📚 Daftar Pustaka"):
            for line in brief["bibliography"].split("\n"):
                if line.strip():
                    st.markdown(line.strip())
