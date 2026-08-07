import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px

from app.components.sidebar import load_custom_css, render_app_sidebar
from app.components.chatbot import render_topic_chatbot
from app.core.auth import render_auth_sidebar
from app.services.clustering_service import clustering_service
from app import api_bridge

# Konfigurasi Halaman[cite: 15]
st.set_page_config(page_title="Scraping & Database", layout="wide", page_icon="📥")

load_custom_css()
render_app_sidebar(active_page="pages/1_Scraping.py")
render_auth_sidebar()

@st.dialog("💬 Tanya AI", width="large")
def _render_chat_dialog():
    """Popup chat AI, sumbernya artikel tersimpan untuk keyword yang dipilih.
    @st.dialog mewarisi perilaku st.fragment -- interaksi widget di dalamnya
    (selectbox, chat_input) hanya me-rerun dialog ini, BUKAN seluruh halaman,
    jadi popup tetap terbuka otomatis di setiap giliran chat tanpa perlu
    flag session_state manual untuk "tetap terbuka"."""
    try:
        df_chat_source = pd.DataFrame(api_bridge.get_articles(limit=500))
        chat_keyword_options = (
            list(df_chat_source["kata_kunci"].dropna().unique())
            if not df_chat_source.empty and "kata_kunci" in df_chat_source.columns else []
        )

        if not chat_keyword_options:
            st.info("Belum ada artikel tersimpan. Jalankan scraping di tab '📥 Scrape Berita' terlebih dahulu.")
            return

        current_kw_chat = st.session_state.get("current_keyword")
        default_idx = (
            chat_keyword_options.index(current_kw_chat)
            if current_kw_chat in chat_keyword_options else 0
        )
        selected_chat_keyword = st.selectbox(
            "Pilih Keyword untuk Dijadikan Basis Chat",
            options=chat_keyword_options,
            index=default_idx,
            key="chat_keyword_selector",
        )

        df_chat_kw = df_chat_source[df_chat_source["kata_kunci"] == selected_chat_keyword]
        chat_sources = df_chat_kw.to_dict(orient="records")

        render_topic_chatbot(
            topic_label=selected_chat_keyword,
            sources=chat_sources,
            session_key=f"scraping::{selected_chat_keyword}",
            empty_hint=f"Belum ada artikel tersimpan untuk keyword '{selected_chat_keyword}'.",
            height=380,
        )
    except Exception as e:
        st.error(f"Gagal memuat data untuk Tanya AI: {e}")


# Header Halaman Utama[cite: 15]
col_header, col_chat_trigger = st.columns([5, 1])
with col_header:
    st.markdown("# 📥 News Intelligence")
    st.caption("Google News Intelligence & Executive Summary")
    st.markdown("Masukkan kata kunci untuk mengambil data berita terbaru dan hasilkan executive summary.")
with col_chat_trigger:
    st.write("")
    st.write("")
    if st.button("💬 Tanya AI", key="open_chat_dialog_btn", width='stretch'):
        _render_chat_dialog()
st.markdown("---")

is_admin = st.session_state.get("role") == "admin"

tab_scrape, tab_history, tab_cluster = st.tabs(
    ["📥 Scrape Berita", "🗄️ Riwayat Ringkasan", "🧩 Story Clustering & Timeline"]
)

# ==================== TAB 1: SCRAPE BERITA ====================
with tab_scrape:
    with st.container(key="scraping_form_card"):
        st.subheader("⚙️ Parameter Pencarian Berita")
        st.write("Masukkan topik atau kata kunci berita (Pencarian otomatis difilter dari 1 Januari 2026)[cite: 15].")
        
        with st.form("scraping_form"):
            keyword = st.text_input("Kata Kunci (Keyword):", st.session_state.get("current_keyword", "Transformasi Digital Indonesia"))
            
            col_a, col_b = st.columns(2)
            with col_a:
                num_results = st.number_input("Jumlah Maksimal Artikel:", min_value=5, max_value=50, value=15, step=5)
            with col_b:
                sentiment_filter = st.selectbox("Filter Sentimen (Opsional Tampilan)", ["Semua", "Positif", "Netral", "Negatif"])

            save_summary_to_db = st.checkbox(
                "💾 Simpan Executive Summary ke Database",
                value=False,
                help="Kalau dimatikan (default), ringkasan hanya dipakai untuk PDF di sesi ini dan tidak ditulis ke tabel executive_summaries di Supabase.",
            )

            submit_scraping = st.form_submit_button("🚀 Gather & Generate Summary", width='stretch', type="primary")

    if submit_scraping:
        if not keyword.strip():
            st.error("Keyword tidak boleh kosong!")
        else:
            st.session_state["current_keyword"] = keyword
            st.session_state["save_summary_to_db"] = save_summary_to_db
            st.write(f"**Proses Scraping Berjalan via API:** '{keyword}'")

            status_text = st.empty()
            progress_bar = st.progress(0)
            with st.spinner("Server sedang memproses ekstraksi artikel dan summary..."):
                try:
                    data = api_bridge.execute_scraping(
                        keyword=keyword, num_results=num_results,
                        status_container=status_text, progress_bar=progress_bar,
                    )
                    fetched = data.get("fetched_count", 0)
                    processed = data.get("processed_count", 0)
                    saved = data.get("saved_count", 0)
                    warning = data.get("warning")

                    progress_bar.progress(1.0)
                    if saved > 0:
                        status_text.success("Gathering selesai.")
                        st.success(
                            f"✅ Ditemukan {fetched} entri, {processed} berhasil diproses, "
                            f"{saved} tersimpan sebagai artikel baru."
                        )
                        st.session_state["trigger_auto_summary"] = keyword
                    else:
                        status_text.warning("Gathering selesai, tapi tidak ada artikel baru tersimpan.")
                        st.warning(warning or "Tidak ada artikel baru yang tersimpan. Lihat app.log untuk detail.")
                        st.session_state["trigger_auto_summary"] = None
                except Exception as e:
                    progress_bar.progress(1.0)
                    st.error(f"Gagal memproses gathering: {e}")
                    st.session_state["trigger_auto_summary"] = None

    st.divider()

    # --- BAGIAN OTOMATIS DOWNLOAD SETELAH SCRAPING ---
    active_keyword_to_summarize = st.session_state.get("trigger_auto_summary")

    if active_keyword_to_summarize:
        st.subheader(f"📥 Laporan Executive Summary Siap: '{active_keyword_to_summarize}'")
        try:
            pdf_bytes, err = api_bridge.generate_summary_pdf(
                active_keyword_to_summarize,
                save_to_db=st.session_state.get("save_summary_to_db", False),
            )
            if pdf_bytes:
                st.toast(f"Laporan '{active_keyword_to_summarize}' siap diunduh!", icon="✅")
                st.success("Laporan analisis berhasil disiapkan dari sistem.")
                st.download_button(
                    label=f"📄 Download PDF Laporan '{active_keyword_to_summarize}'",
                    data=pdf_bytes,
                    file_name=f"Laporan_Executive_Summary_{active_keyword_to_summarize.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    width='stretch'
                )
            else:
                st.error(f"Laporan belum tersedia: {err}")
        except Exception as e:
            st.error(f"Gagal membuat PDF: {e}")
    else:
        st.info("Jalankan scraping di atas untuk melihat laporan Executive Summary di sini.")


# ==================== TAB 2: RIWAYAT RINGKASAN ====================
with tab_history:
    st.subheader("🗄️ Daftar Executive Summary Tersimpan (Database)")
    
    try:
        df_latest = pd.DataFrame(api_bridge.get_articles(limit=500))
        if True:
            if not df_latest.empty and 'kata_kunci' in df_latest.columns:
                unique_keywords = df_latest['kata_kunci'].dropna().unique()
                
                for kw in unique_keywords:
                    df_kw = df_latest[df_latest['kata_kunci'] == kw]
                    total_art = len(df_kw)
                    
                    with st.expander(f"🔑 Topik / Kata Kunci: {kw} ({total_art} Artikel Terkait)"):
                        col_info1, col_info2 = st.columns([3, 1])
                        with col_info1:
                            st.markdown("**Status Dokumen:** Siap Diunduh")
                            st.markdown(f"**Total Artikel Terkumpul:** {total_art} entri")
                        with col_info2:
                            if st.button(f"📥 Unduh PDF", key=f"btn_dl_{kw.replace(' ', '_')}", width='stretch'):
                                with st.spinner(f"Memproses file PDF untuk '{kw}'..."):
                                    pdf_bytes, err = api_bridge.generate_summary_pdf(kw)
                                    if pdf_bytes:
                                        st.download_button(
                                            label=f"Klik Untuk Unduh File '{kw}'",
                                            data=pdf_bytes,
                                            file_name=f"Laporan_Executive_Summary_{kw.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                                            mime="application/pdf",
                                            key=f"dl_action_{kw.replace(' ', '_')}",
                                            width='stretch'
                                        )
                                    else:
                                        st.error(f"Gagal mendapatkan PDF: {err}")
            else:
                st.info("Belum ada data berita tersimpan di database.")
    except Exception as e:
        st.error(f"Terjadi kesalahan saat memuat riwayat: {e}")


# ==================== TAB 3: STORY CLUSTERING & TIMELINE ====================
with tab_cluster:
    st.subheader("🧩 Pengelompokan Cerita (Story Clustering) & Timeline")
    st.caption("Artikel yang membahas peristiwa/isu yang sama otomatis dikelompokkan menjadi satu 'cerita'[cite: 15].")

    try:
        df_for_cluster = pd.DataFrame(api_bridge.get_articles(limit=500))
        if True:
            if df_for_cluster.empty:
                st.info("Belum ada data berita untuk dianalisis clustering.")
            else:
                cluster_keyword_options = (
                    list(df_for_cluster["kata_kunci"].dropna().unique())
                    if "kata_kunci" in df_for_cluster.columns else []
                )
                current_kw = st.session_state.get("current_keyword")
                default_cluster_kw = [current_kw] if current_kw in cluster_keyword_options else cluster_keyword_options[:1]

                col_ck1, col_ck2 = st.columns([3, 1])
                with col_ck1:
                    selected_cluster_keywords = st.multiselect(
                        "Pilih Keyword untuk Dianalisis",
                        options=cluster_keyword_options,
                        default=default_cluster_kw,
                        key="cluster_keyword_filter",
                    )
                with col_ck2:
                    run_cluster = st.button("🧩 Jalankan Clustering", width='stretch')

                if run_cluster:
                    scoped_df = (
                        df_for_cluster[df_for_cluster["kata_kunci"].isin(selected_cluster_keywords)]
                        if selected_cluster_keywords and "kata_kunci" in df_for_cluster.columns
                        else df_for_cluster
                    )
                    if scoped_df.empty:
                        st.warning("Tidak ada artikel untuk keyword yang dipilih.")
                    else:
                        with st.spinner("Mengelompokkan artikel berdasarkan kemiripan isi (TF-IDF + clustering)..."):
                            clustered_df = clustering_service.cluster(scoped_df)
                            summary_df = clustering_service.build_cluster_summary(clustered_df)

                        n_stories = summary_df.shape[0] if not summary_df.empty else clustered_df["cluster_id"].nunique()
                        st.success(f"✅ {len(scoped_df)} artikel dikelompokkan menjadi {n_stories} cerita (story).")

                        if not summary_df.empty:
                            st.dataframe(
                                summary_df.rename(columns={
                                    "cluster_label": "Judul Perwakilan",
                                    "jumlah_artikel": "Jumlah Artikel",
                                    "tanggal_mulai": "Mulai",
                                    "tanggal_akhir": "Terakhir",
                                    "media_terlibat": "Media Terlibat",
                                }),
                                width='stretch', hide_index=True,
                            )

                        timeline_fig = clustering_service.build_timeline_fig(clustered_df)
                        if timeline_fig:
                            st.plotly_chart(timeline_fig, width='stretch')
                        else:
                            st.caption("Timeline tidak dapat ditampilkan (butuh kolom tanggal yang valid pada artikel).")
                else:
                    st.caption("Pilih keyword (opsional) lalu klik **Jalankan Clustering** untuk mengelompokkan artikel menjadi cerita & melihat timeline-nya.")
                
        else:
            st.error("Gagal mengambil data dari server.")
    except Exception as e:
        st.error(f"Terjadi kesalahan koneksi: {e}")