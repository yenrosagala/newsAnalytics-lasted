"""Service RINGKASAN BERITA (news summary) untuk halaman Scraping.

Menghasilkan esai naratif {title, summary} dari korpus berita/media hasil
scraping -- BUKAN Executive Intelligence Brief S-R-I-R (itu milik halaman AI
Investigator / Fenomena, lihat decision_brief). Dipakai:
  - halaman Scraping berita (pages/1_Scraping.py)
  - halaman Social Media Scraper (pages/5_Social_Media_Scraper.py)

Menggantikan executive_summary_service lama yang membuat brief S-R-I-R.
"""
import json
import re
from collections import Counter
from typing import List, Optional

import pandas as pd

from app.core.logger import get_logger
from app.prompts.news_summary import get_news_summary_system_prompt, get_news_summary_user_prompt
from app.services.ai_service import ai_service
from app.services.database_service import db_service
from app.services.pdf_service import generate_pdf_report, fig_to_png_buffer
from app.services.geo_service import build_location_hotspots
from app.core.theme import SENTIMENT_COLORS

logger = get_logger("NewsSummaryService")

MAX_ARTICLES_FOR_SUMMARY = 50
MAX_PROMPT_CHARS = 200000
MAX_ARTICLE_TEXT_CHARS = 10000
MIN_SUMMARY_CHARS = 200  # di bawah ini dianggap keluaran rusak (mis. "User Safety: safe") -> ulangi
MAX_SUMMARY_ATTEMPTS = 3

SUMMARY_SECTION_TITLE = "Ringkasan Berita"

# Kata fungsi umum untuk menebak bahasa keluaran AI tanpa library deteksi
# bahasa. Model gratis kadang mengabaikan instruksi "WAJIB Bahasa Indonesia".
_ID_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "dengan", "untuk", "pada", "tidak",
    "ini", "itu", "adalah", "akan", "juga", "karena", "sebagai", "oleh",
    "dalam", "atau", "tersebut", "lebih", "sudah", "bisa", "telah", "para",
    "sehingga", "namun", "saat", "hingga", "antara", "masih",
}
_EN_STOPWORDS = {
    "the", "and", "of", "to", "in", "is", "was", "with", "that", "for", "on",
    "as", "are", "were", "this", "it", "from", "by", "at", "has", "have",
    "but", "not", "be", "been", "its", "their", "which", "while", "these",
}


def _looks_indonesian(text: str) -> bool:
    """True kalau teks condong Bahasa Indonesia. Kalau tak ada kata fungsi yang
    dikenali sama sekali, jangan menghukum (anggap True) supaya tidak salah
    mengulang hanya karena kosakata yang tidak terduga."""
    tokens = re.findall(r"[a-zA-Z]+", (text or "").lower())
    if not tokens:
        return False
    id_hits = sum(1 for t in tokens if t in _ID_STOPWORDS)
    en_hits = sum(1 for t in tokens if t in _EN_STOPWORDS)
    if id_hits == 0 and en_hits == 0:
        return True
    return id_hits >= en_hits


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


def _select_articles_for_prompt(articles: List[dict]) -> List[dict]:
    """Artikel yang benar-benar masuk ke prompt: dibatasi jumlah artikel DAN
    total panjang karakter. Dipakai bersama oleh _build_concatenated_content()
    dan _build_bibliography() supaya nomor sitasi [n] konsisten dengan daftar
    pustaka yang ditampilkan."""
    selected = []
    total_len = 0
    for idx, article in enumerate(articles[:MAX_ARTICLES_FOR_SUMMARY], start=1):
        block = _sanitize_article_block(article, idx)
        if total_len + len(block) > MAX_PROMPT_CHARS:
            break
        selected.append(article)
        total_len += len(block)
    return selected


def _build_concatenated_content(articles: List[dict]) -> str:
    blocks = [
        _sanitize_article_block(article, idx)
        for idx, article in enumerate(_select_articles_for_prompt(articles), start=1)
    ]
    return "\n---\n".join(blocks)


def _build_bibliography(articles: List[dict]) -> List[dict]:
    """Daftar sumber bernomor [n] yang PERSIS cocok dengan blok bernomor yang
    dikirim ke model, supaya sitasi [n] di esai merujuk sumber yang benar."""
    bibliography = []
    for idx, article in enumerate(_select_articles_for_prompt(articles), start=1):
        bibliography.append({
            "n": idx,
            "media": article.get("media") or article.get("source") or "Unknown",
            "title": article.get("title") or article.get("judul") or "[Tanpa Judul]",
            "date": article.get("waktu_tampilan") or article.get("published_date") or "",
            "url": article.get("url") or article.get("link") or "",
        })
    return bibliography


def _format_bibliography(bibliography: List[dict]) -> str:
    """Format teks daftar pustaka bernomor untuk PDF (satu baris per sumber)."""
    lines = []
    for entry in bibliography:
        label = f"[{entry.get('n')}] {entry.get('media') or '-'} -- {entry.get('title') or '-'}"
        if entry.get("date"):
            label += f" ({entry['date']})"
        if entry.get("url"):
            label += f". {entry['url']}"
        lines.append(label)
    return "\n".join(lines)


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
        "Gunakan data ini sebagai konteks untuk menyusun ringkasan berita."
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


def _parse_summary_json(raw, fallback_title: str) -> dict:
    """Ambil {title, summary} dari keluaran AI. Toleran terhadap: JSON valid,
    JSON dibungkus code fence/teks, ATAU prosa markdown biasa (model kadang
    mengabaikan permintaan "JSON saja" -- tanpa force_json, response_format
    json_object ditolak sebagian model/endpoint). Kalau teks diawali heading
    "# ...", heading dipakai sebagai judul dan sisanya sebagai summary."""
    text = raw if isinstance(raw, str) else str(raw or "")
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            title = str(obj.get("title") or "").strip()
            summary = str(obj.get("summary") or "").strip()
            if summary:
                return {"title": title or fallback_title, "summary": summary}
        except Exception:
            pass
    # Fallback prosa/markdown: pakai heading pertama sebagai judul.
    m = re.match(r"^#{1,6}\s*(.+?)\s*\n", text + "\n")
    if m:
        heading = re.sub(r"^Ringkasan Berita\s*[:\-]\s*", "", m.group(1).strip(), flags=re.I).strip()
        body = text[m.end():].strip()
        if body:
            return {"title": heading or fallback_title, "summary": body}
    return {"title": fallback_title, "summary": text}


def _build_offline_summary(keyword: str, articles: List[dict], date_range_str: str, top_media_str: str) -> dict:
    top_keywords = _extract_topic_keywords(articles)
    topic_summary = ", ".join(top_keywords[:3]) if top_keywords else keyword
    sources = []
    for article in articles:
        source = article.get("media") or article.get("source") or "Unknown"
        if source not in sources:
            sources.append(source)
        if len(sources) >= 5:
            break

    title = f"Ringkasan Berita {keyword} (Offline)"
    summary = (
        f"Ringkasan ini disusun secara offline dari {len(articles)} artikel yang berkaitan dengan kata kunci "
        f"'{keyword}'. Rentang waktu publikasi adalah {date_range_str}, dengan media kontributor teratas "
        f"{top_media_str}. Dari judul-judul artikel, topik yang paling menonjol berkisar pada {topic_summary}.\n\n"
        "Karena layanan AI tidak tersedia saat ringkasan dibuat, ikhtisar ini hanya dibentuk dari judul, sumber, "
        "dan potongan awal konten yang tersedia. Media yang paling sering muncul juga cenderung mendominasi narasi "
        "sehingga sudut pandang lain bisa kurang terwakili.\n\n"
        f"Sumber yang tercakup antara lain: {', '.join(sources) if sources else 'tidak tersedia'}. "
        "Gunakan ringkasan ini sebagai gambaran awal, bukan sebagai kesimpulan akhir, dan baca artikel lengkap "
        "untuk konteks yang lebih utuh."
    )
    return {"title": title, "summary": summary}


class NewsSummaryService:
    def generate_summary(self, keyword: str, articles: List[dict], save_to_db: bool = False) -> dict:
        """Kembalikan {"title", "summary"} berupa esai naratif dari korpus berita."""
        if not articles:
            return {
                "title": f"Ringkasan Berita {keyword}",
                "summary": "Tidak ada artikel yang tersedia untuk kata kunci ini.",
                "bibliography": [],
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

        system_prompt = get_news_summary_system_prompt(
            display_title_keyword=keyword,
            date_range_str=date_range_str,
            t_media_str=top_media_str,
        )
        user_prompt = get_news_summary_user_prompt(
            data_context=_build_data_context(keyword, articles, date_range_str, top_media_str),
            concatenated_content=concatenated_content,
            catatan_regenerate=note,
        )

        summary = None
        fallback_candidate = None  # esai valid tapi (mungkin) bukan Bahasa Indonesia
        for attempt in range(1, MAX_SUMMARY_ATTEMPTS + 1):
            try:
                raw = ai_service.generate(user_prompt, force_json=False, system_prompt=system_prompt)
            except Exception as e:
                logger.warning(f"Percobaan {attempt}: gagal memanggil AI ({e}).")
                continue
            candidate = _parse_summary_json(raw, fallback_title=f"Ringkasan Berita {keyword}")
            body = (candidate.get("summary") or "").strip()
            # Model gratis kadang mengembalikan keluaran rusak (mis. label
            # klasifikasi "User Safety: safe") alih-alih esai. Esai valid jauh
            # lebih panjang dari MIN_SUMMARY_CHARS -> deteksi & ulangi.
            if len(body) < MIN_SUMMARY_CHARS:
                logger.warning(f"Percobaan {attempt}: keluaran AI tidak valid/terlalu pendek ({len(body)} char), mengulang.")
                continue
            if fallback_candidate is None:
                fallback_candidate = candidate
            if _looks_indonesian(body):
                summary = candidate
                break
            logger.warning(f"Percobaan {attempt}: ringkasan terdeteksi bukan Bahasa Indonesia, mengulang.")

        if summary is None:
            # Pakai esai valid non-Indonesia daripada jatuh ke ringkasan offline.
            summary = fallback_candidate
        if summary is None:
            logger.error("Ringkasan berita AI gagal setelah semua percobaan; memakai ringkasan offline.")
            summary = _build_offline_summary(keyword, articles, date_range_str, top_media_str)

        if not summary.get("title"):
            summary["title"] = f"Ringkasan Berita {keyword}"

        summary["bibliography"] = _build_bibliography(articles)

        if save_to_db:
            try:
                db_service.save_executive_summary_to_db(
                    keyword, date_range_str, json.dumps(summary, ensure_ascii=False)
                )
            except Exception as e:
                logger.warning(f"Gagal menyimpan cache ringkasan berita: {e}")

        return summary

    def create_pdf_bytes(
        self, keyword: str, articles: List[dict], summary: Optional[dict] = None, save_to_db: bool = False
    ) -> bytes:
        """summary: kirim Ringkasan Berita yang sudah dibuat (mis. lewat
        generate_summary()) agar AI tidak dipanggil dua kali ketika ringkasan
        sudah ditampilkan inline sebelum PDF diunduh. Kalau None, ringkasan
        dibuat baru. save_to_db diteruskan ke generate_summary() bila summary
        belum ada -- default False."""
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

        summary = summary or self.generate_summary(keyword, articles, save_to_db=save_to_db)
        date_range_str = _get_date_range_str(articles)
        top_media_str = _get_top_media_str(articles)

        # Renderer PDF mengharapkan dict "brief"; esai naratif ditaruh di
        # `situation`, sisanya dikosongkan. plain_body=True mematikan subjudul
        # S-R-I-R dan brief_section_title mengganti judul seksi.
        brief = {
            "title": summary.get("title", keyword),
            "situation": summary.get("summary", ""),
            "risks": [],
            "impact": "",
            "recommendations": [],
            "bibliography": _format_bibliography(summary.get("bibliography") or []),
        }

        extra_graphs = []
        spatial_buf = self._build_spatial_map_buffer(df)
        if spatial_buf is not None:
            extra_graphs.append(("Peta Sebaran Lokasi Berita (Spatial Intelligence)", spatial_buf))

        return generate_pdf_report(
            df, [], keyword, date_range_str, top_media_str, brief,
            extra_graphs=extra_graphs,
            brief_section_title=SUMMARY_SECTION_TITLE,
            plain_body=True,
        )

    @staticmethod
    def _build_spatial_map_buffer(df: pd.DataFrame):
        """Bangun peta hotspot lokasi (Plotly scatter_geo) dan rasterisasi ke PNG
        untuk PDF. Return None kalau data kosong / tidak ada lokasi / gagal
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
                color_discrete_map=SENTIMENT_COLORS,
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


news_summary_service = NewsSummaryService()
