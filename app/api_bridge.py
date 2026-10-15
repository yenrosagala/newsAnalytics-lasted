"""
In-process replacement for the old FastAPI backend (app/main.py + app/api/endpoints/*).

Why this exists
----------------
The previous architecture ran two separate processes: a Streamlit frontend
and a FastAPI backend (uvicorn on :8000), talking to each other over HTTP
(`requests.get/post("http://localhost:8000/...")`). That works locally but
is INCOMPATIBLE with Streamlit Community Cloud / Streamlit-in-Claude, which
only runs a single process — there is no way to also boot a uvicorn server
next to it, so every `requests.*` call to API_BASE_URL just fails.

Fix: call the same service-layer functions the FastAPI endpoints used to
call, directly, in-process. No HTTP, no second server, same business logic.
Each function below mirrors one FastAPI route 1:1.
"""
from typing import Optional

from app.core.logger import get_logger
from app.services.database_service import db_service, DatabaseConnectionError
from app.services.scraper_service import scraper_service
from app.services.social_scraper_service import social_scraper_service
from app.services.news_summary_service import news_summary_service
from app.services.ai_service import ai_service
from app.services.predictive_service import (
    build_daily_volume_series,
    classify_trend,
    forecast_linear,
    detect_anomalies_robust_zscore,
    generate_alerts,
)
from app.services.recursive_engine import (
    run_recursive_5why_pipeline_with_progress,
    consolidate_bibliography,
    format_level_breakdown_for_prompt,
    format_bibliography_for_prompt,
    validate_citation_diversity,
    build_evidence_graph_data,
)
from app.services.decision_brief import parse_decision_brief_json, deserialize_brief
from app.services.pdf_service import generate_pdf_report, fig_to_png_buffer
from app.services.evidence_graph import build_evidence_graph_fig
from app.services.actor_graph import extract_actors_per_level, build_actor_graph_data, build_actor_graph_fig
from app.prompts.executive_summary import get_recursive_executive_summary_prompt

logger = get_logger("ApiBridge")


# ---- scraping.py -----------------------------------------------------------

def execute_scraping(
    keyword: str, num_results: int = 15, status_container=None, progress_bar=None
) -> dict:
    result = scraper_service.execute_scraping_workflow(
        keyword=keyword, limit=num_results, region="ID",
        status_container=status_container, progress_bar=progress_bar,
    )
    return {"status": "success", "keyword": keyword, **result}


def generate_news_summary(keyword: str) -> tuple[Optional[dict], Optional[str]]:
    """Returns (summary, error). Ringkasan berita naratif {title, summary} dari
    korpus berita tersimpan untuk suatu keyword, untuk ditampilkan inline di
    halaman Scraping. Tidak menulis ke DB."""
    try:
        df = db_service.get_latest_scraped_data(limit=1000)
    except DatabaseConnectionError as e:
        return None, f"Gagal terhubung ke database (bukan 'data kosong'): {e}"

    if df.empty:
        return None, "Data kosong."
    df_kw = df[df["kata_kunci"] == keyword] if "kata_kunci" in df.columns else df
    if df_kw.empty:
        return None, f"Tidak ada data untuk keyword '{keyword}'."

    articles = df_kw.to_dict(orient="records")
    try:
        return news_summary_service.generate_summary(keyword, articles), None
    except Exception as e:
        return None, f"Gagal membangun ringkasan berita: {e}"


def generate_news_summary_pdf(
    keyword: str, summary: Optional[dict] = None, save_to_db: bool = False
) -> tuple[Optional[bytes], Optional[str]]:
    """Returns (pdf_bytes, error). Ringkasan Berita (news summary) PDF untuk
    suatu keyword. Kirim `summary` hasil generate_news_summary() agar AI tidak
    dipanggil dua kali. save_to_db: default False -- ringkasan hanya dipakai
    untuk PDF ini, tidak otomatis ditulis ke tabel executive_summaries."""
    try:
        df = db_service.get_latest_scraped_data(limit=1000)
    except DatabaseConnectionError as e:
        return None, f"Gagal terhubung ke database (bukan 'data kosong'): {e}"

    if df.empty:
        return None, "Data kosong."
    df_kw = df[df["kata_kunci"] == keyword] if "kata_kunci" in df.columns else df
    if df_kw.empty:
        return None, f"Tidak ada data untuk keyword '{keyword}'."

    articles = df_kw.to_dict(orient="records")
    try:
        pdf_bytes = news_summary_service.create_pdf_bytes(
            keyword, articles, summary=summary, save_to_db=save_to_db
        )
        return pdf_bytes, None
    except Exception as e:
        return None, f"Gagal membangun PDF ringkasan berita: {e}"


# ---- dashboard.py -----------------------------------------------------------

def get_dashboard_metrics(keyword: Optional[str] = None, media: Optional[str] = None) -> dict:
    df = db_service.get_latest_scraped_data(limit=1000)
    if df.empty:
        return {"total_berita": 0, "portal_unik": 0, "keyword_aktif": 0}
    if keyword:
        df = df[df["kata_kunci"] == keyword]
    if media:
        df = df[df["media"] == media]
    return {
        "total_berita": len(df),
        "portal_unik": int(df["media"].nunique()) if "media" in df.columns else 0,
        "keyword_aktif": int(df["kata_kunci"].nunique()) if "kata_kunci" in df.columns else 0,
    }


def get_articles(limit: int = 100) -> list:
    df = db_service.get_latest_scraped_data(limit=limit)
    return df.to_dict(orient="records")


def delete_articles_by_date(date_str: str, admin_password: str) -> int:
    return db_service.delete_articles_by_date(date_str, admin_password)


# ---- investigator.py --------------------------------------------------------

async def run_investigation(
    initial_query: str, max_depth: int = 5, status_text=None, progress_bar=None, save_to_db: bool = False
) -> dict:
    """Pipeline lengkap AI Investigator: recursive 5-Why -> konsolidasi
    daftar pustaka -> Executive Brief (AI) -> evidence graph.
    Sebelumnya fungsi ini hanya mengembalikan result_tree, sehingga panel
    Executive Brief di halaman selalu kosong -- diperbaiki di sini supaya
    'brief', 'consolidated_bib', 'graph_data', 'citation_warning' yang
    diharapkan pages/3_Fenomena.py benar-benar terisi.
    save_to_db: default False -- hasil investigasi (result_tree + executive
    summary) hanya dipakai untuk sesi ini, tidak otomatis ditulis ke tabel
    root_cause_analyses di Supabase.
    """
    result_tree = await run_recursive_5why_pipeline_with_progress(
        initial_query=initial_query, max_depth=max_depth,
        status_text=status_text, progress_bar=progress_bar,
    )
    if not result_tree:
        raise ValueError("Tidak ada data ditemukan.")

    consolidated_bib = consolidate_bibliography(result_tree)

    brief_system_prompt, brief_user_prompt = get_recursive_executive_summary_prompt(
        initial_query=initial_query,
        level_breakdown=format_level_breakdown_for_prompt(result_tree),
        numbered_bibliography=format_bibliography_for_prompt(consolidated_bib),
    )
    try:
        raw_brief = ai_service.generate(brief_user_prompt, force_json=True, system_prompt=brief_system_prompt)
    except Exception as e:
        logger.error(f"Gagal membuat Executive Brief: {e}")
        raw_brief = ""

    fallback_title = f"Analisis Akar Masalah: {initial_query}"
    brief = parse_decision_brief_json(raw_brief, fallback_title=fallback_title)
    citation_warning = validate_citation_diversity(brief.get("situation", ""), consolidated_bib)
    graph_data = build_evidence_graph_data(result_tree)

    if save_to_db:
        try:
            db_service.save_root_cause_analysis(
                initial_query=initial_query, result_tree=result_tree, executive_summary=brief.get("situation", ""),
            )
        except Exception as e:
            logger.warning(f"Gagal menyimpan riwayat root cause analysis: {e}")

    return {
        "status": "success",
        "result_tree": result_tree,
        "brief": brief,
        "consolidated_bib": consolidated_bib,
        "graph_data": graph_data,
        "citation_warning": citation_warning,
    }


# ---- predictive.py -----------------------------------------------------------

def get_predictive_analysis(keyword: str, forecast_horizon: int = 7) -> dict:
    df = db_service.get_latest_scraped_data(limit=1000)
    if df.empty:
        raise ValueError("Data kosong.")
    df_kw = df[df["kata_kunci"] == keyword]
    daily_volume = build_daily_volume_series(df_kw)
    if daily_volume.empty or len(daily_volume) < 3:
        raise ValueError("Data historis tidak mencukupi.")

    trend_info = classify_trend(daily_volume)
    anomalies_df = detect_anomalies_robust_zscore(daily_volume)
    alerts = generate_alerts(keyword, trend_info, anomalies_df)
    forecast = forecast_linear(daily_volume, horizon_days=forecast_horizon)

    return {
        "trend_info": trend_info,
        "alerts": alerts,
        "anomalies": anomalies_df.to_dict(orient="records"),
        "forecast": forecast if forecast else None,
        "daily_volume": {
            "date": [d.strftime("%Y-%m-%d") for d in daily_volume.index],
            "count": daily_volume.values.tolist(),
            "ma7_count": daily_volume.rolling(7, min_periods=1).mean().values.tolist(),
        },
    }


def get_latest_brief() -> tuple[Optional[str], Optional[dict], Optional[str], Optional[str]]:
    """Returns (keyword, brief, created_at, error). Mengambil SATU Executive
    Brief paling baru lintas semua keyword, untuk beranda "Briefs" -- supaya
    pengguna yang tidak sempat baca berita langsung disambut brief siap pakai,
    bukan menu tool yang harus dioperasikan dulu."""
    row = db_service.get_latest_executive_summary()
    if not row:
        return None, None, None, None
    keyword = row.get("kata_kunci")
    try:
        brief = deserialize_brief(row.get("hasil_summary"), fallback_title=f"Executive Summary {keyword}")
    except Exception as e:
        return keyword, None, row.get("created_at"), f"Gagal membaca brief tersimpan: {e}"
    return keyword, brief, row.get("created_at"), None


# ---- social_scraping.py ------------------------------------------------------

SOCIAL_PLATFORMS = ["facebook", "instagram", "youtube", "threads", "twitter"]


def execute_social_scraping(
    platform: str, target: str, limit: int = 20,
    keyword: Optional[str] = None, headless: bool = True,
    status_container=None, progress_bar=None,
) -> dict:
    result = social_scraper_service.execute_social_scraping_workflow(
        platform=platform,
        target=target,
        limit=limit,
        keyword=keyword,
        headless=headless,
        status_container=status_container,
        progress_bar=progress_bar,
    )
    return {"status": "success", **result}


def _load_social_posts_for_keyword(keyword: str) -> tuple[Optional[list[dict]], Optional[str]]:
    df = db_service.get_latest_social_posts(limit=1000)
    if df.empty:
        return None, "Data kosong."
    df_kw = df[df["keyword"] == keyword] if "keyword" in df.columns else df
    if df_kw.empty:
        return None, f"Tidak ada data untuk keyword '{keyword}'."
    return df_kw.to_dict(orient="records"), None


def generate_social_summary(keyword: str) -> tuple[Optional[dict], list[dict], Optional[str]]:
    """Returns (summary, posts, error). Membuat Ringkasan Berita naratif dari
    post media sosial yang tersimpan untuk suatu keyword, TANPA merender PDF --
    dipakai untuk menampilkan ringkasan langsung di halaman."""
    posts, err = _load_social_posts_for_keyword(keyword)
    if err:
        return None, [], err
    try:
        summary = news_summary_service.generate_summary(keyword, posts)
        return summary, posts, None
    except Exception as e:
        return None, posts, f"Gagal membangun ringkasan sosial: {e}"


def generate_social_summary_pdf(
    keyword: str, summary: Optional[dict] = None, posts: Optional[list[dict]] = None
) -> tuple[Optional[bytes], Optional[str]]:
    """Returns (pdf_bytes, error). Ringkasan Berita PDF untuk post media sosial
    per keyword. Pass `summary`/`posts` yang sudah dihasilkan sebelumnya (mis.
    dari generate_social_summary) supaya AI tidak dipanggil dua kali."""
    if posts is None:
        posts, err = _load_social_posts_for_keyword(keyword)
        if err:
            return None, err

    try:
        pdf_bytes = news_summary_service.create_pdf_bytes(keyword, posts, summary=summary)
        return pdf_bytes, None
    except Exception as e:
        return None, f"Gagal membangun PDF ringkasan sosial: {e}"


# ---- Fenomena.py (AI Investigator) -----------------------------------------

def generate_decision_brief_pdf(
    title: str,
    brief: dict,
    result_tree: Optional[list] = None,
    actor_graph_data: Optional[dict] = None,
    consolidated_bib: Optional[list] = None,
) -> tuple[Optional[bytes], Optional[str]]:
    """Returns (pdf_bytes, error). Renders the recursive AI Investigator's
    Decision Intelligence Executive Brief (Situation/Risks/Impact/
    Recommendations/Bibliography) as a standalone PDF -- no article table
    involved, so charts and the Insights section are simply omitted by
    generate_pdf_report() when there's no article DataFrame.

    This reuses the exact same renderer as generate_news_summary_pdf() /
    generate_social_summary_pdf(); previously nothing called it for the
    recursive investigator, so pages/3_Fenomena.py showed a permanently
    disabled button instead.

    `result_tree`: optional -- when given, the Evidence Graph (root-cause
    chain) is rasterized and embedded. `actor_graph_data`: optional --
    when given (e.g. from st.session_state["last_actor_graph_data"], since
    building it calls the AI and shouldn't happen twice), the Peta Aktor
    graph is rasterized and embedded too. Both are skipped silently if not
    provided or if there isn't enough data to build them.

    `consolidated_bib`: optional -- the globally-numbered bibliography built
    by `consolidate_bibliography(result_tree)` (see run_investigation()),
    e.g. from st.session_state["last_consolidated_bibliography"]. This is
    the list the AI's own [n] citations in `brief["situation"]`/`impact`
    actually refer to. `brief["bibliography"]` is intentionally left empty
    by the AI Investigator prompt (the system builds it, not the model --
    see decision_brief.py / prompts/executive_summary.py), so without this
    the PDF's "Daftar Pustaka" section had nothing to show even though the
    Streamlit page displays the sources fine. When provided, it's formatted
    and used to fill that section.
    """
    if not brief:
        return None, "Belum ada Executive Brief untuk dijadikan PDF."
    try:
        import pandas as pd

        if consolidated_bib and not brief.get("bibliography"):
            brief = dict(brief)
            lines = []
            for entry in consolidated_bib:
                levels_str = ", ".join(f"L{d}" for d in entry.get("levels", []))
                lines.append(
                    f"[{entry.get('number', '?')}] {entry.get('author', 'Tidak diketahui')}. "
                    f"{entry.get('media', '-')}. {entry.get('date', '-')}. "
                    f"{entry.get('title', 'Tanpa Judul')}. {entry.get('url', '')} "
                    f"(Ditemukan di: {levels_str})"
                )
            brief["bibliography"] = "\n".join(lines)

        extra_graphs = []
        if result_tree:
            try:
                evidence_data = build_evidence_graph_data(result_tree)
                evidence_fig = build_evidence_graph_fig(evidence_data)
                evidence_buf = fig_to_png_buffer(evidence_fig, width=900, height=700)
                if evidence_buf is not None:
                    extra_graphs.append(("Evidence Graph -- Peta Bukti & Alur Investigasi", evidence_buf))
            except Exception as e:
                logger.warning(f"Gagal merender Evidence Graph untuk PDF: {e}")

        if actor_graph_data:
            try:
                actor_fig = build_actor_graph_fig(actor_graph_data)
                actor_buf = fig_to_png_buffer(actor_fig, width=900, height=700)
                if actor_buf is not None:
                    extra_graphs.append(("Peta Aktor -- Orang & Institusi Lintas Level", actor_buf))
            except Exception as e:
                logger.warning(f"Gagal merender Peta Aktor untuk PDF: {e}")

        pdf_bytes = generate_pdf_report(
            filtered_df=pd.DataFrame(),
            insights=[],
            target_keyword=title,
            date_range_str="-",
            t_media_str="-",
            brief=brief,
            extra_graphs=extra_graphs,
        )
        return pdf_bytes, None
    except Exception as e:
        return None, f"Gagal membangun PDF Executive Intelligence Brief: {e}"


def generate_actor_graph(result_tree: list) -> tuple[Optional[dict], Optional[str]]:
    """Returns (graph_data, error). Mengekstrak entitas (orang/institusi) dari
    summary + causes_extracted tiap level (satu panggilan AI per level, TANPA
    fetch ulang artikel), lalu menyusun satu graf gabungan lintas level:
    entitas yang sama muncul di beberapa level jadi SATU node dengan banyak
    edge -- merepresentasikan aktor yang "menjembatani" level investigasi
    yang berbeda."""
    if not result_tree:
        return None, "Belum ada hasil investigasi."
    try:
        actors_by_depth = extract_actors_per_level(result_tree)
        graph_data = build_actor_graph_data(result_tree, actors_by_depth)
        return graph_data, None
    except Exception as e:
        return None, f"Gagal membangun peta aktor: {e}"