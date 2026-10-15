from datetime import datetime

import pandas as pd
import streamlit as st

from app.components.social_summary import render_social_summary
from app.components.news_summary_view import render_news_summary
from app.core.page import setup_page
from app import api_bridge

setup_page("Social Media Scraper", "🌐", "pages/5_Social_Media_Scraper.py")

st.markdown("# 🌐 Social Media Scraper")
st.caption("Scraping konten publik dari Facebook, Instagram, YouTube, Threads, dan X/Twitter (Selenium).")
st.warning(
    "⚠️ **Batasan penting:** modul ini hanya mengakses konten **publik**, tanpa login "
    "otomatis. Facebook, Instagram, Threads, dan X/Twitter melarang scraping otomatis "
    "di Terms of Service masing-masing -- gunakan sesuai kebijakan platform & hukum "
    "yang berlaku (mis. UU PDP/GDPR untuk data pribadi). Untuk kebutuhan produksi, "
    "pertimbangkan API resmi platform (mis. YouTube Data API, Meta Graph API)."
)
st.markdown("---")

with st.container(key="social_scraping_form_card"):
    st.subheader("⚙️ Parameter Scraping")
    with st.form("social_scraping_form"):
        col1, col2 = st.columns(2)
        with col1:
            platform = st.selectbox(
                "Platform",
                ["all", "youtube", "facebook", "instagram", "threads", "twitter"],
                help="Pilih 'all' untuk menjalankan scraping serentak di semua platform yang didukung."
            )
        with col2:
            target = st.text_input(
                "Target",
                placeholder="@handle, URL profil/page publik, atau kata kunci pencarian/topik",
            )

        col3, col4 = st.columns(2)
        with col3:
            limit = st.number_input("Jumlah Maksimal Post/Video", min_value=5, max_value=100, value=20, step=5)
        with col4:
            keyword_tag = st.text_input("Label Kata Kunci (opsional, untuk grouping di dashboard)")

        submit_social = st.form_submit_button(
            "🚀 Jalankan Scraping", width='stretch', type="primary"
        )

if submit_social:
    if not target.strip():
        st.error("Target tidak boleh kosong!")
    else:
        status_text = st.empty()
        progress_bar = st.progress(0)
        with st.spinner(f"Membuka browser headless & mengambil data dari {platform}..."):
            try:
                data = api_bridge.execute_social_scraping(
                    platform=platform,
                    target=target,
                    limit=int(limit),
                    keyword=keyword_tag or None,
                    status_container=status_text,
                    progress_bar=progress_bar,
                )
                fetched = data.get("fetched_count", 0)
                saved = data.get("saved_count", 0)

                if fetched == 0:
                    progress_bar.progress(1.0)
                    status_text.warning(
                        "Tidak ada post yang berhasil diambil. Kemungkinan penyebab: "
                        "target memerlukan login (platform menampilkan dinding login), "
                        "target tidak ditemukan, atau struktur halaman berubah sehingga "
                        "selector perlu disesuaikan. Cek app.log untuk detail."
                    )
                else:
                    progress_bar.progress(1.0)
                    status_text.success("Scraping selesai.")
                    st.success(f"✅ Berhasil mengambil {fetched} post, tersimpan {saved} ke database.")
                    posts_df = pd.DataFrame(data.get("posts", []))
                    st.dataframe(posts_df, width='stretch')
                    st.download_button(
                        "📄 Download CSV",
                        data=posts_df.to_csv(index=False).encode("utf-8"),
                        file_name=f"social_{platform}_{target.strip('@')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                    )

                    st.markdown("---")
                    # Ringkasan statistik instan -- tidak butuh AI, langsung dari
                    # post yang baru diambil (lihat app/components/social_summary.py).
                    render_social_summary(posts_df)

                    st.markdown("---")
                    pdf_keyword = keyword_tag.strip() if keyword_tag else target.strip()
                    if pdf_keyword:
                        st.markdown("### 🧠 Ringkasan Naratif (AI)")
                        with st.spinner("Membuat ringkasan naratif AI dari post yang terkumpul..."):
                            summary, summary_posts, summary_err = api_bridge.generate_social_summary(pdf_keyword)

                        if summary:
                            render_news_summary(summary)
                            try:
                                pdf_bytes, pdf_err = api_bridge.generate_social_summary_pdf(
                                    pdf_keyword, summary=summary, posts=summary_posts
                                )
                                if pdf_bytes:
                                    safe_name = "".join(
                                        c if c.isalnum() or c in " _-" else "_" for c in pdf_keyword
                                    )[:80]
                                    st.download_button(
                                        label=f"📄 Download PDF Ringkasan Sosial '{pdf_keyword}'",
                                        data=pdf_bytes,
                                        file_name=f"Ringkasan_Sosial_{safe_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                                        mime="application/pdf",
                                        width='stretch',
                                    )
                                else:
                                    st.warning(f"PDF ringkasan sosial tidak tersedia: {pdf_err}")
                            except Exception as e:
                                st.error(f"Gagal membuat PDF ringkasan sosial: {e}")
                        else:
                            st.warning(f"Ringkasan naratif AI tidak tersedia: {summary_err}")
                    elif platform == "all":
                        st.info(
                            "Tip: beri Label Kata Kunci agar sistem dapat membuat ringkasan naratif AI dari semua posting sosial yang dikumpulkan untuk target ini."
                        )
            except Exception as e:
                progress_bar.progress(1.0)
                status_text.error(f"Gagal memproses scraping: {e}")
                st.error(f"Gagal memproses scraping: {e}")

st.markdown("---")
st.caption(
    "Chrome headless via Selenium dijalankan langsung di proses Streamlit ini "
    "(app/services/social_scraper_service.py). Pastikan Google Chrome/Chromium terpasang di environment."
)
