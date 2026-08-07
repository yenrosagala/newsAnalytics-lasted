from datetime import datetime
import streamlit as st

from app.core.auth import render_auth_sidebar
from app.core.config import Config
from app.core.logger import setup_logger
from app.components.decision_brief_view import render_decision_brief
from app.components.chatbot import render_topic_chatbot
from app.components.sidebar import load_custom_css, render_app_sidebar
from app.services.evidence_graph import build_evidence_graph_fig
from app.services.actor_graph import build_actor_graph_fig
from app import api_bridge

config = Config()
logger = setup_logger("page_fenomena")

# Konfigurasi Halaman[cite: 17]
st.set_page_config(page_title="AI Investigator", layout="wide", page_icon="🕵️")

load_custom_css()
render_app_sidebar(active_page="pages/3_Fenomena.py")
render_auth_sidebar()

st.markdown("# 🕵️ AI Investigator")
st.caption("Recursive Root Cause Analysis · Evidence Graph (Terintegrasi API)")
st.markdown("Telusuri akar masalah secara mendalam berdasarkan temuan berita...[cite: 17]")
st.markdown("---")

def _render_level_details(level_info: dict, depth: int, total_levels: int, url_to_global_number: dict | None = None):
    is_root_cause = depth == total_levels
    root_badge = "🎯 " if is_root_cause else ""
    expander_label = f"{root_badge}Level {depth}: {', '.join(level_info.get('queries_used', []))}"

    with st.expander(expander_label, expanded=(depth == 1)):
        if is_root_cause:
            st.markdown('<span class="root-cause-badge">🎯 Root Cause Level</span>', unsafe_allow_html=True)
        if level_info.get("ai_call_failed"):
            st.warning(
                f"⚠️ AI gagal dipanggil di level ini (semua provider gagal) -- ringkasan/penyebab "
                f"di bawah TIDAK LENGKAP, investigasi dihentikan lebih awal karena ini, bukan "
                f"karena akar masalah sudah ditemukan. Detail: {level_info['ai_call_failed']}"
            )
        st.markdown(f"<p style='color: #64748b; margin-bottom: 8px;'><b>Artikel Diekstrak:</b> {level_info.get('articles_found', 0)} artikel</p>", unsafe_allow_html=True)

        if level_info.get("summary"):
            st.markdown(f"<p style='color: #374357;'><b>📝 Ringkasan Level:</b> {level_info['summary']}</p>", unsafe_allow_html=True)

        if level_info.get("causes_extracted"):
            st.markdown("<b>🔍 Penyebab Teridentifikasi (dengan Skor Keyakinan):</b>", unsafe_allow_html=True)
            _tier_colors = {"Tinggi": "#10b981", "Sedang": "#f59e0b", "Rendah": "#ef4444"}
            for c in level_info["causes_extracted"]:
                if isinstance(c, dict):
                    detail = c.get("confidence_detail") or {}
                    composite = detail.get("composite")
                    tier = detail.get("tier", "Rendah")
                    color = _tier_colors.get(tier, "#64748b")
                    badge = f"<span style='background:{color}22; color:{color}; border:1px solid {color}66; border-radius:6px; padding:1px 8px; font-size:0.72rem; font-weight:700; margin-left:6px;'>{composite}% · {tier}</span>" if composite is not None else ""
                    st.markdown(f"- {c.get('cause', '')} {badge}", unsafe_allow_html=True)
                    if c.get("rationale"):
                        st.markdown(f"<p style='color:#64748b; font-size:0.82rem; margin:0 0 6px 16px;'>↳ {c['rationale']}</p>", unsafe_allow_html=True)
                else:
                    st.markdown(f"- 🔴 {c}")

        if level_info.get("bibliography"):
            st.markdown(f"**📚 Daftar Pustaka Level {depth}**")
            url_to_global_number_local = url_to_global_number or {}
            for local_idx, bib in enumerate(level_info["bibliography"], 1):
                num = url_to_global_number_local.get(bib.get("url"), local_idx)
                st.markdown(f"[{num}] {bib.get('author', 'Tidak diketahui')}. {bib.get('media', '-')}. {bib.get('date', '-')}. **{bib.get('title', 'Tanpa Judul')}**. [Link]({bib.get('url', '#')})")

        if level_info.get("next_keywords"):
            st.markdown("**➡️ Keyword Turunan:**")
            st.info(" | ".join([f"`{kw}`" for kw in level_info["next_keywords"]]))

def _render_evidence_graph_section(result_tree: list, graph_data: dict):
    st.caption("Peta bukti interaktif[cite: 17]")
    fig = build_evidence_graph_fig(graph_data)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Belum cukup data untuk membangun evidence graph.")

def _build_and_cache_actor_graph(query_key: str, result_tree: list):
    with st.spinner("Mengekstrak aktor per level & membangun peta..."):
        graph_data, err = api_bridge.generate_actor_graph(result_tree)
    if err:
        st.session_state["last_actor_graph_key"] = None
        st.session_state["last_actor_graph_data"] = None
        st.session_state["last_actor_graph_error"] = err
    else:
        st.session_state["last_actor_graph_key"] = query_key
        st.session_state["last_actor_graph_data"] = graph_data
        st.session_state["last_actor_graph_error"] = None

def _render_actor_graph_section(query_key: str, result_tree: list):
    st.caption("Orang & institusi yang disebut terlibat di tiap level investigasi, dan bagaimana mereka menjembatani level yang berbeda. Diekstrak dari ringkasan & penyebab yang sudah ada -- tidak fetch ulang artikel.[cite: 17]")
    cached_key = st.session_state.get("last_actor_graph_key")
    cached_data = st.session_state.get("last_actor_graph_data")

    if cached_key == query_key and cached_data:
        fig = build_actor_graph_fig(cached_data)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Tidak ada aktor (orang/institusi) yang teridentifikasi secara eksplisit di ringkasan investigasi ini.")
        if st.button("🔄 Bangun Ulang Peta Aktor", use_container_width=True, key=f"regen_actor_{query_key}"):
            _build_and_cache_actor_graph(query_key, result_tree)
            st.rerun()
    else:
        err = st.session_state.get("last_actor_graph_error")
        if err:
            st.error(f"Gagal membangun peta aktor: {err}")
        st.info("Peta aktor belum dibangun untuk investigasi ini. Proses ini memanggil AI sekali per level (tidak fetch ulang artikel).")
        if st.button("🧑‍🤝‍🧑 Bangun Peta Aktor (AI)", type="primary", use_container_width=True, key=f"build_actor_{query_key}"):
            _build_and_cache_actor_graph(query_key, result_tree)
            st.rerun()

@st.dialog("💬 Tanya AI", width="large")
def _render_fenomena_chat_dialog(query_key: str, consolidated_bib: list):
    """Popup chat AI, sumbernya daftar pustaka konsolidasi investigasi ini.
    @st.dialog mewarisi perilaku st.fragment -- chat_input di dalamnya
    hanya me-rerun dialog ini, jadi popup tetap terbuka otomatis di setiap
    giliran chat tanpa perlu flag session_state manual."""
    st.caption("Chat AI ini hanya menjawab berdasarkan daftar pustaka konsolidasi hasil investigasi ini -- bukan pengetahuan umum di luar itu.")
    render_topic_chatbot(
        topic_label=query_key,
        sources=consolidated_bib,
        session_key=f"fenomena::{query_key}",
        empty_hint="Belum ada daftar pustaka untuk investigasi ini.",
        height=380,
    )

def _render_investigation_results(title: str, brief: dict, citation_warning: str | None, result_tree: list, consolidated_bib: list, graph_data: dict):
    query_key = st.session_state.get("last_recursive_query", title)

    col_title, col_chat_trigger = st.columns([5, 1])
    with col_title:
        st.markdown(f"## {title}")
    with col_chat_trigger:
        if st.button("💬 Tanya AI", key=f"open_chat_dialog::{query_key}", use_container_width=True):
            _render_fenomena_chat_dialog(query_key, consolidated_bib)

    sub_tab_brief, sub_tab_graph, sub_tab_actors, sub_tab_tree = st.tabs(
        ["📋 Executive Brief", "🕸️ Evidence Graph", "🧑‍🤝‍🧑 Peta Aktor", "🌳 Root Cause Tree"]
    )

    with sub_tab_brief:
        render_decision_brief(brief)
        if citation_warning:
            st.warning(citation_warning)

    with sub_tab_graph:
        _render_evidence_graph_section(result_tree, graph_data)

    with sub_tab_actors:
        _render_actor_graph_section(st.session_state.get("last_recursive_query", ""), result_tree)

    with sub_tab_tree:
        total_levels = max((lvl["depth"] for lvl in result_tree), default=1)
        url_to_global_number = {b.get("url"): b.get("number") for b in consolidated_bib}
        for level_info in result_tree:
            _render_level_details(level_info, level_info["depth"], total_levels, url_to_global_number)

# --- STRUKTUR TAB UTAMA ---
tab_recursive, tab_pdf_recursive = st.tabs(["🕵️ Jalankan AI Investigator", "📄 Download Executive Intelligence Brief"])

with tab_recursive:
    with st.container(key="fenomena_config_card"):
        st.subheader("⚙️ Konfigurasi Investigasi")
        initial_problem_query = st.text_area("Deskripsi Fenomena / Masalah Utama", value=st.session_state.get("last_recursive_query", "Sensus Ekonomi 2026 Papua kendala"))
        depth = st.slider("Kedalaman Analisis (Recursive Level)", 3, 7, 5)
        save_investigation_to_db = st.checkbox(
            "💾 Simpan Hasil Investigasi ke Database",
            value=False,
            help="Kalau dimatikan (default), hasil root cause analysis & executive brief hanya dipakai untuk sesi ini dan tidak ditulis ke tabel root_cause_analyses di Supabase.",
        )
        run_analysis = st.button("🕵️ Jalankan AI Investigator", type="primary", use_container_width=True)

    st.markdown("---")

    if run_analysis:
        with st.status("🕵️ AI Investigator Server sedang bekerja...", expanded=True) as status_box:
            try:
                import asyncio
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                data = asyncio.run(
                    api_bridge.run_investigation(
                        initial_query=initial_problem_query, max_depth=depth,
                        status_text=status_text, progress_bar=progress_bar,
                        save_to_db=save_investigation_to_db,
                    )
                )
                st.session_state["last_recursive_result"] = data.get("result_tree", [])
                st.session_state["last_recursive_query"] = initial_problem_query
                st.session_state["last_decision_brief"] = data.get("brief", {})
                st.session_state["last_report_title"] = data.get("brief", {}).get("title", f"Analisis Akar Masalah: {initial_problem_query}")
                st.session_state["last_consolidated_bibliography"] = data.get("consolidated_bib", [])
                st.session_state["last_graph_data"] = data.get("graph_data", {})
                st.session_state["last_citation_warning"] = data.get("citation_warning")

                status_box.update(label="✅ Investigasi selesai!", state="complete", expanded=False)
                st.success("✅ Analisis Akar Masalah (5 Why) & Penyusunan Laporan Eksekutif Selesai!")

                _render_investigation_results(
                    st.session_state["last_report_title"],
                    st.session_state["last_decision_brief"],
                    st.session_state["last_citation_warning"],
                    st.session_state["last_recursive_result"],
                    st.session_state["last_consolidated_bibliography"],
                    st.session_state["last_graph_data"]
                )
            except Exception as e:
                status_box.update(label="❌ Terjadi kesalahan sistem", state="error")
                st.error(f"Gagal mengeksekusi pipeline: {e}")
    else:
        stored_result_history = st.session_state.get("last_recursive_result", None)
        if not stored_result_history:
            st.markdown(
                """<div class="feature-card" style="text-align: center; padding: 48px 24px; border: 2px dashed rgba(32, 107, 196, 0.25);">
                <div style="font-size: 3rem; margin-bottom: 12px;">🕵️</div>
                <h3 style="color: #2563eb;">Belum Ada Investigasi yang Dijalankan</h3>
                <p style="color: #64748b; max-width: 600px; margin: 0 auto 20px auto;">
                    Masukkan deskripsi fenomena di atas dan klik tombol <b>Jalankan AI Investigator</b>. 
                </p></div>""", unsafe_allow_html=True
            )
        else:
            _render_investigation_results(
                st.session_state.get("last_report_title", ""),
                st.session_state.get("last_decision_brief", {}),
                st.session_state.get("last_citation_warning"),
                stored_result_history,
                st.session_state.get("last_consolidated_bibliography", []),
                st.session_state.get("last_graph_data", {})
            )

with tab_pdf_recursive:
    st.subheader("📄 Cetak & Download Executive Intelligence Brief (PDF)")
    stored_result = st.session_state.get("last_recursive_result", None)
    stored_query = st.session_state.get("last_recursive_query", "Analisis Fenomena")
    stored_title = st.session_state.get("last_report_title", f"Analisis Akar Masalah: {stored_query}")

    if not stored_result:
        st.warning("⚠️ Belum ada hasil investigasi yang tersedia.")
    else:
        st.info(f"💡 Executive Intelligence Brief **'{stored_title}'** siap dicetak[cite: 17].")
        stored_brief = st.session_state.get("last_decision_brief", {})
        cached_actor_key = st.session_state.get("last_actor_graph_key")
        cached_actor_data = st.session_state.get("last_actor_graph_data")
        actor_graph_for_pdf = cached_actor_data if cached_actor_key == stored_query else None
        if not actor_graph_for_pdf:
            st.caption(
                "ℹ️ Peta Aktor belum dibangun untuk investigasi ini -- bangun dulu di tab "
                "'🕵️ Jalankan AI Investigator' > Evidence Graph agar ikut disertakan di PDF."
            )

        if st.button("📥 Proses Executive Intelligence Brief (PDF)", type="primary", use_container_width=True):
            with st.spinner("Membangun PDF Executive Intelligence Brief..."):
                pdf_bytes, err = api_bridge.generate_decision_brief_pdf(
                    stored_title, stored_brief,
                    result_tree=stored_result,
                    actor_graph_data=actor_graph_for_pdf,
                    consolidated_bib=st.session_state.get("last_consolidated_bibliography", []),
                )
            if pdf_bytes:
                st.download_button(
                    label="Klik Untuk Unduh Executive Intelligence Brief (PDF)",
                    data=pdf_bytes,
                    file_name=f"Executive_Intelligence_Brief_{stored_query.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    key="dl_decision_brief_pdf",
                    use_container_width=True,
                )
            else:
                st.error(f"Gagal membuat PDF: {err}")