import datetime
import re
from collections import Counter
from typing import Dict, List, Optional

import pandas as pd

from app.core.logger import get_logger
from app.prompts.executive_summary import get_executive_summary_system_prompt, get_executive_summary_user_prompt
from app.services.ai_service import ai_service
from app.services.database_service import db_service
from app.services.decision_brief import parse_decision_brief_json, serialize_brief
from app.services.pdf_service import generate_pdf_report, fig_to_png_buffer
from app.services.geo_service import build_location_hotspots

logger = get_logger("ExecutiveSummaryService")

MAX_ARTICLES_FOR_SUMMARY = 15
MAX_PROMPT_CHARS = 28000
MAX_ARTICLE_TEXT_CHARS = 2500


def _sanitize_article_block(article: dict, index: int) -> str:
    title = article.get("title") or article.get("judul")
    platform = article.get("platform") or article.get("media") or article.get("source")
    author = article.get("author")
    if not title:
        if author and platform:
            title = f"Posting {platform.capitalize()} oleh {author}"
        elif platform:
            title = f"Posting {platform.capitalize()}"
        else:
            title = "[Tanpa Judul]"

    source = article.get("media") or article.get("source") or platform or "Unknown"
    published_date = (
        article.get("published_date")
        or article.get("waktu_tampilan")
        or article.get("posted_at")
        or "Unknown"
    )
    url = article.get("url") or article.get("link") or ""
    content = article.get("content") or article.get("isi_konten") or ""
    if len(content) > MAX_ARTICLE_TEXT_CHARS:
        content = content[:MAX_ARTICLE_TEXT_CHARS].rsplit(" ", 1)[0] + "\n[...konten dipangkas untuk menjaga batas prompt...]"

    return (
        f"[{index}] {title}\n"
        f"Source: {source}\n"
        f"Date: {published_date}\n"
        f"URL: {url}\n"
        f"{content}\n"
    )


def _build_concatenated_content(articles: List[dict]) -> str:
    blocks = []
    total_len = 0
    for idx, article in enumerate(articles[:MAX_ARTICLES_FOR_SUMMARY], start=1):
        block = _sanitize_article_block(article, idx)
        if total_len + len(block) > MAX_PROMPT_CHARS:
            break
        blocks.append(block)
        total_len += len(block)
    return "\n---\n".join(blocks)


def _get_date_range_str(articles: List[dict]) -> str:
    dates = []
    for article in articles:
        date_value = article.get("published_date") or article.get("waktu_tampilan")
        if date_value:
            dates.append(str(date_value))
    if not dates:
        return "Tidak tersedia"

    try:
        parsed = pd.to_datetime(dates, errors="coerce")
        parsed = parsed.dropna()
        if parsed.empty:
            return "Tidak tersedia"
        start = parsed.min().strftime("%d %B %Y")
        end = parsed.max().strftime("%d %B %Y")
        return f"{start} - {end}" if start != end else start
    except Exception:
        return f"{dates[0]} - {dates[-1]}" if len(dates) > 1 else dates[0]


def _get_top_media_str(articles: List[dict]) -> str:
    counts = Counter()
    for article in articles:
        source = article.get("media") or article.get("source") or "Unknown"
        counts[source] += 1
    if not counts:
        return "Tidak tersedia"
    most_common = counts.most_common(3)
    return ", ".join([f"{source} ({count})" for source, count in most_common])


def _build_data_context(keyword: str, articles: List[dict], date_range_str: str, top_media_str: str) -> str:
    return (
        f"Keyword utama: {keyword}\n"
        f"Total artikel dalam korpus: {len(articles)}\n"
        f"Rentang waktu publikasi: {date_range_str}\n"
        f"Top media kontributor: {top_media_str}\n"
        "Gunakan data ini sebagai konteks untuk membuat Executive Brief yang komprehensif."
    )


def _extract_topic_keywords(articles: List[dict], max_keywords: int = 5) -> List[str]:
    stopwords = {
        "yang", "dari", "dengan", "dan", "ke", "di", "pada", "untuk", "atau",
        "ini", "juga", "sebagai", "oleh", "karena", "pada", "saat", "oleh",
        "adalah", "lebih", "dalam", "mereka", "ini", "tersebut", "pasar",
        "digital", "indonesia", "transformasi", "berita", "media", "online",
    }
    keyword_counts = Counter()
    for article in articles:
        title = str(article.get("title") or article.get("judul") or "")
        for token in re.findall(r"\w+", title.lower()):
            if len(token) < 4 or token in stopwords:
                continue
            keyword_counts[token] += 1
    return [word for word, _ in keyword_counts.most_common(max_keywords)]


def _build_offline_brief(keyword: str, articles: List[dict], date_range_str: str, top_media_str: str) -> dict:
    top_keywords = _extract_topic_keywords(articles)
    topic_summary = ", ".join(top_keywords[:3]) if top_keywords else keyword
    unique_sources = []
    for article in articles:
        source = article.get("media") or article.get("source") or "Unknown"
        if source not in unique_sources:
            unique_sources.append(source)
        if len(unique_sources) >= 5:
            break

    bibliography_items = [f"[{idx}] {source}." for idx, source in enumerate(unique_sources, start=1)]
    bibliography = "\n".join(bibliography_items)

    title = f"Executive Summary {keyword} (Offline)"
    situation = (
        f"Laporan ini disusun secara offline dari {len(articles)} artikel yang berkaitan dengan kata kunci '{keyword}'. "
        f"Rentang waktu publikasi adalah {date_range_str}, dan top media kontributor adalah {top_media_str}. "
        f"Topik utama yang tampak dari judul-judul artikel berfokus pada {topic_summary}. "
        "Karena layanan AI tidak tersedia saat pembuatan laporan, ringkasan ini dibuat dari judul, sumber, dan potongan konten artikel yang tersedia."
    )
    situation += (
        " Sumber berita utama telah dimasukkan sebagai bibliografi untuk membantu verifikasi lebih lanjut. "
        "Gunakan laporan ini sebagai gambaran awal, bukan analisis akhir."
    )

    risks = [
        {
            "risk": "Ringkasan offline dapat kehilangan konteks mendalam karena hanya mengandalkan judul dan kutipan awal artikel.",
            "severity": "Tinggi",
            "rationale": "Analisis ini tidak dilakukan oleh model AI, sehingga detail kebijakan dan implikasi strategis mungkin kurang lengkap.",
        },
        {
            "risk": "Media yang paling sering muncul dapat mendominasi narasi, sementara sumber lain cenderung kurang terwakili.",
            "severity": "Sedang",
            "rationale": "Ringkasan offline dibangun dari sumber yang tersedia tanpa normalisasi lanjutan pada distribusi media.",
        },
        {
            "risk": "Bahasa dan fokus isu bisa menjadi terlalu umum, sehingga beberapa nuansa topik tidak tertangkap secara akurat.",
            "severity": "Rendah",
            "rationale": "Pendekatan heuristik ini menekankan headline dan metadata, bukan sintetis interpretasi kontekstual penuh.",
        },
    ]

    impact = (
        "Ringkasan offline ini masih memberi gambaran umum atas isu yang menonjol dalam korpus berita, khususnya tren dan fokus sumber yang paling sering muncul. "
        "Namun, laporan ini mungkin tidak mencakup seluruh ragam perspektif, dan nilai strategisnya terbatas pada insight permukaan."
    )
    impact += (
        " Untuk keputusan yang memerlukan detail kebijakan atau analisis risiko mendalam, disarankan melengkapi ringkasan ini dengan studi artikel penuh atau dukungan analis manusia yang tersedia."
    )

    recommendations = [
        "Baca ulang artikel lengkap dari sumber utama yang tercantum di bibliografi untuk memastikan konteks dan akurasi informasi.",
        "Gunakan ringkasan offline ini sebagai titik awal diskusi, bukan sebagai kesimpulan final.",
        "Aktifkan kembali akses AI atau libatkan analis manusia begitu layanan eksternal tersedia untuk mendapatkan analisis yang lebih mendalam.",
        "Pantau kembali perkembangan topik ini dalam berita berikutnya untuk menangkap perubahan cepat yang mungkin belum tercakup di laporan ini.",
    ]

    return {
        "title": title,
        "situation": situation,
        "risks": risks,
        "impact": impact,
        "recommendations": recommendations,
        "bibliography": bibliography,
    }


def _build_insights(brief: dict) -> List[str]:
    insights = []
    if brief.get("title"):
        insights.append(brief["title"])
    if brief.get("situation"):
        sentences = [p.strip() for p in brief["situation"].split("\n") if p.strip()]
        insights.extend(sentences[:2])
    if brief.get("risks"):
        insights.extend([r.get("risk", "") for r in brief["risks"] if r.get("risk")])
    if len(insights) < 3:
        insights.append("Executive summary disusun dari korpus berita terkait kata kunci.")
    return insights


class ExecutiveSummaryService:
    def generate_executive_summary(self, keyword: str, articles: List[dict], save_to_db: bool = False) -> dict:
        if not articles:
            return {
                "title": f"Executive Summary {keyword}",
                "situation": "Tidak ada artikel yang tersedia untuk kata kunci ini.",
                "risks": [],
                "impact": "",
                "recommendations": [],
                "bibliography": "",
            }

        date_range_str = _get_date_range_str(articles)
        top_media_str = _get_top_media_str(articles)
        concatenated_content = _build_concatenated_content(articles)
        note = ""
        if len(articles) > MAX_ARTICLES_FOR_SUMMARY:
            note = (
                "Catatan: korpus berita sangat besar dan hanya sebagian dokumen terpilih yang digunakan "
                "sebagai sumber ringkasan untuk menjaga batas prompt."
            )

        system_prompt = get_executive_summary_system_prompt(
            display_title_keyword=keyword,
            date_range_str=date_range_str,
            t_media_str=top_media_str,
        )
        user_prompt = get_executive_summary_user_prompt(
            data_context=_build_data_context(keyword, articles, date_range_str, top_media_str),
            concatenated_content=concatenated_content,
            catatan_regenerate=note,
        )

        try:
            raw = ai_service.generate(user_prompt, force_json=True, system_prompt=system_prompt)
            brief = parse_decision_brief_json(raw, fallback_title=f"Executive Summary {keyword}")
        except Exception as e:
            logger.error(f"Gagal membuat executive summary AI: {e}")
            brief = _build_offline_brief(keyword, articles, date_range_str, top_media_str)

        if not brief.get("title"):
            brief["title"] = f"Executive Summary {keyword}"

        if save_to_db:
            try:
                db_service.save_executive_summary_to_db(keyword, date_range_str, serialize_brief(brief))
            except Exception as e:
                logger.warning(f"Gagal menyimpan cache executive summary: {e}")

        return brief

    def create_pdf_bytes(
        self, keyword: str, articles: List[dict], brief: Optional[dict] = None, save_to_db: bool = False
    ) -> bytes:
        """brief: kirim Executive Brief yang sudah pernah dibuat (mis. lewat
        generate_executive_summary()) untuk menghindari memanggil AI dua kali
        ketika ringkasan sudah ditampilkan inline sebelum PDF diunduh. Kalau
        None, brief akan dibuat baru seperti perilaku sebelumnya.
        save_to_db: teruskan ke generate_executive_summary() kalau brief belum
        ada -- default False supaya hasil generate tidak otomatis masuk DB."""
        df = pd.DataFrame(articles)
        if not df.empty:
            rename_map = {
                "keyword": "kata_kunci",
                "source": "media",
                "title": "judul",
                "content": "isi_konten",
                "published_date": "waktu_tampilan",
                "sentiment": "Sentimen",
            }
            df = df.rename(columns=rename_map)

        brief = brief or self.generate_executive_summary(keyword, articles, save_to_db=save_to_db)
        attempts = brief.get("title", keyword)
        date_range_str = _get_date_range_str(articles)
        top_media_str = _get_top_media_str(articles)
        insights = _build_insights(brief)

        extra_graphs = []
        spatial_buf = self._build_spatial_map_buffer(df)
        if spatial_buf is not None:
            extra_graphs.append(("Peta Sebaran Lokasi Berita (Spatial Intelligence)", spatial_buf))

        return generate_pdf_report(
            df, insights, keyword, date_range_str, top_media_str, brief,
            extra_graphs=extra_graphs,
        )

    @staticmethod
    def _build_spatial_map_buffer(df: pd.DataFrame):
        """Bangun peta hotspot lokasi (Plotly scatter_geo, sama seperti tab
        Spatial Intelligence di Dashboard) dan rasterisasi ke PNG untuk PDF.
        Return None kalau data kosong / tidak ada lokasi terdeteksi / gagal
        render -- PDF tetap valid tanpa peta ini."""
        if df is None or df.empty or "judul" not in df.columns:
            return None
        try:
            hotspots_df = build_location_hotspots(
                df, title_col="judul", content_col="isi_konten",
                sentiment_col="Sentimen" if "Sentimen" in df.columns else None,
            )
            if hotspots_df.empty:
                return None

            import plotly.express as px

            fig = px.scatter_geo(
                hotspots_df,
                lat="lat", lon="lon",
                size="mention_count",
                hover_name="location",
                color="dominant_sentiment",
                color_discrete_map={
                    "Positive": "#10b981", "Negative": "#ef4444", "Neutral": "#64748b",
                    "POSITIVE": "#10b981", "NEGATIVE": "#ef4444", "NEUTRAL": "#64748b",
                },
                projection="natural earth",
                title="Sebaran Hotspot Berita di Indonesia",
            )
            fig.update_geos(
                center=dict(lat=-2.5, lon=118),
                projection_scale=4.2,
                showcountries=True, countrycolor="#c7ccd6",
            )
            fig.update_layout(margin=dict(t=48, b=10, l=10, r=10))
            return fig_to_png_buffer(fig, width=850, height=550)
        except Exception as e:
            logger.warning(f"Gagal membangun peta spasial untuk PDF: {e}")
            return None


executive_summary_service = ExecutiveSummaryService()