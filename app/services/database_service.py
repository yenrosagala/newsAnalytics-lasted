import json
import pandas as pd
import uuid
from supabase import create_client, Client
from app.core.logger import get_logger
from app.core.config import Config, _get_secret

logger = get_logger("DatabaseService")


class DatabaseConnectionError(Exception):
    """Raised when a Supabase read/write genuinely fails (bad credentials,
    network error, missing table, etc.) as opposed to the query legitimately
    returning zero rows. Callers should catch this specifically and show the
    user an actionable message instead of silently treating it as 'no data'."""
    pass


class DatabaseService:
    """Service layer untuk menangani interaksi dengan Supabase."""

    def __init__(self):
        self.supabase_url = _get_secret("SUPABASE_URL", "")
        self.default_api_key = _get_secret("SUPABASE_ANON_KEY", "")

        if not self.supabase_url or not self.default_api_key:
            logger.error(
                "SUPABASE_URL dan/atau SUPABASE_ANON_KEY belum dikonfigurasi di st.secrets. "
                "Buat file .streamlit/secrets.toml (lokal) atau isi menu Settings > Secrets "
                "(Streamlit Cloud) dengan kedua key tersebut."
            )

    def _get_client(self, custom_api_key: str = None) -> Client:
        """Helper untuk membuat client dengan opsional API Key (untuk admin)."""
        if not self.supabase_url:
            raise ValueError("SUPABASE_URL belum dikonfigurasi di st.secrets!")
        api_key = custom_api_key or self.default_api_key
        if not api_key:
            raise ValueError("SUPABASE_ANON_KEY belum dikonfigurasi di st.secrets!")
        return create_client(self.supabase_url, api_key)

    def get_latest_scraped_data(self, limit: int = 1000) -> pd.DataFrame:
        """Mengambil data berita terbaru dengan pembersihan kolom."""
        try:
            client = self._get_client()
            response = client.table("news_articles").select("*").order("id", desc=True).limit(limit).execute()

            if not response.data:
                return pd.DataFrame()

            df = pd.DataFrame(response.data)

            # Mapping kolom untuk menjaga kompatibilitas dengan UI lama
            mapping = {
                "keyword": "kata_kunci",
                "title": "judul",
                "source": "media",
                "published_date": "waktu_tampilan",
                "content": "isi_konten",
                "sentiment": "Sentimen"
            }
            return df.rename(columns=mapping)
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise DatabaseConnectionError(
                f"Gagal terhubung/mengambil data dari Supabase: {e}"
            ) from e

    def check_status(self) -> dict:
        """Cek konektivitas Supabase secara RINGAN (limit=1) -- dipakai oleh
        status bar di setiap halaman. Return: {"ok": bool, "detail": str}."""
        if not self.supabase_url or not self.default_api_key:
            return {"ok": False, "detail": "SUPABASE_URL/SUPABASE_ANON_KEY belum dikonfigurasi di secrets.toml"}
        try:
            client = self._get_client()
            client.table("news_articles").select("id").limit(1).execute()
            return {"ok": True, "detail": "Terhubung"}
        except Exception as e:
            return {"ok": False, "detail": f"Gagal terhubung: {e}"}

    def save_articles(self, articles: list) -> int:
        """Menyimpan/Upsert artikel dengan proteksi UUID."""
        if not articles:
            return 0

        try:
            client = self._get_client()
            payload = [self._prepare_article_row(art) for art in articles]
            response = client.table("news_articles").upsert(payload).execute()
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Error saving articles: {e}")
            return 0

    def delete_articles_by_date(self, date_str: str, admin_password: str) -> int:
        """
        Menghapus artikel berdasarkan tanggal dengan validasi kata sandi admin.
        Mengembalikan jumlah baris yang terhapus (0 jika gagal/password salah).
        """
        if not admin_password or admin_password != Config.ADMIN_PASSWORD:
            logger.warning("Upaya akses ilegal ke fitur penghapusan massal (password salah).")
            return 0

        try:
            # Password admin hanya dipakai untuk otorisasi level-aplikasi.
            # Koneksi ke Supabase tetap memakai kredensial default yang sudah dikonfigurasi.
            client = self._get_client()
            start_dt = f"{date_str}T00:00:00"
            end_dt = f"{date_str}T23:59:59"

            response = (
                client.table("news_articles")
                .delete()
                .gte("published_date", start_dt)
                .lte("published_date", end_dt)
                .execute()
            )
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Error deleting articles: {e}")
            return 0

    # ------------------------------------------------------------------
    # Social media posts (dipakai oleh Social Media Scraper / Selenium)
    # ------------------------------------------------------------------
    def save_social_posts(self, posts: list) -> int:
        """Menyimpan/Upsert post media sosial ke tabel social_posts."""
        if not posts:
            return 0
        try:
            client = self._get_client()
            payload = [self._prepare_social_post_row(p) for p in posts]
            response = client.table("social_posts").upsert(payload).execute()
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Error saving social posts: {e}")
            return 0

    def get_latest_social_posts(self, platform: str = None, limit: int = 500) -> pd.DataFrame:
        """Mengambil post media sosial terbaru, opsional difilter per platform."""
        try:
            client = self._get_client()
            query = client.table("social_posts").select("*").order("id", desc=True).limit(limit)
            if platform:
                query = query.eq("platform", platform)
            response = query.execute()
            if not response.data:
                return pd.DataFrame()
            return pd.DataFrame(response.data)
        except Exception as e:
            logger.error(f"Error fetching social posts: {e}")
            return pd.DataFrame()

    def _prepare_social_post_row(self, post: dict) -> dict:
        """Helper untuk normalisasi format post medsos sebelum masuk DB."""
        url = post.get("url", "")
        row_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url)) if url else str(uuid.uuid4())

        posted_at = post.get("posted_at")
        if hasattr(posted_at, "isoformat"):
            posted_at = posted_at.isoformat()

        return {
            "id": row_id,
            "platform": post.get("platform"),
            "author": post.get("author"),
            "content": post.get("content"),
            "url": url,
            "posted_at": str(posted_at) if posted_at else None,
            "likes": post.get("likes"),
            "comments": post.get("comments"),
            "shares": post.get("shares"),
            "keyword": post.get("keyword"),
        }

    # ------------------------------------------------------------------
    # Executive Summary caching (dipakai oleh halaman Scraping)
    # ------------------------------------------------------------------
    def get_cached_executive_summary(self, keyword: str):
        """Mengambil executive summary yang sudah pernah dibuat untuk keyword ini, jika ada."""
        try:
            client = self._get_client()
            response = (
                client.table("executive_summaries")
                .select("hasil_summary")
                .eq("kata_kunci", keyword)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0].get("hasil_summary")
            return None
        except Exception as e:
            logger.warning(f"Tidak bisa mengambil cache executive summary (cek tabel 'executive_summaries'): {e}")
            return None

    def get_latest_executive_summary(self) -> dict | None:
        """Mengambil SATU executive summary paling baru lintas semua keyword --
        dipakai oleh Home ("Briefs") supaya pengguna langsung disambut brief
        terbaru begitu buka aplikasi, tanpa harus tahu/pilih keyword dulu.
        Return dict {kata_kunci, hasil_summary, created_at} atau None kalau
        belum ada brief sama sekali (atau tabel tidak terjangkau)."""
        try:
            client = self._get_client()
            response = (
                client.table("executive_summaries")
                .select("kata_kunci, hasil_summary, created_at")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.warning(f"Tidak bisa mengambil executive summary terbaru (cek tabel 'executive_summaries'): {e}")
            return None

    def save_executive_summary_to_db(self, kata_kunci: str, rentang_waktu: str, hasil_summary: str) -> bool:
        """Menyimpan hasil executive summary AI agar bisa dipakai ulang (cache)."""
        try:
            client = self._get_client()
            client.table("executive_summaries").insert({
                "kata_kunci": kata_kunci,
                "rentang_waktu": rentang_waktu,
                "hasil_summary": hasil_summary,
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Gagal menyimpan executive summary (cek tabel 'executive_summaries'): {e}")
            return False

    # ------------------------------------------------------------------
    # Root Cause Analysis / Recursive 5-Why (dipakai oleh halaman Fenomena)
    # ------------------------------------------------------------------
    def save_root_cause_analysis(self, initial_query: str, result_tree: list, executive_summary: str) -> bool:
        """Menyimpan hasil analisis 5-Why bertingkat ke database sebagai riwayat."""
        try:
            client = self._get_client()
            client.table("root_cause_analysis").insert({
                "initial_query": initial_query,
                "result_tree" : json.loads(json.dumps(result_tree, default=str)),
                "executive_summary": executive_summary,
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Gagal menyimpan root cause analysis (cek tabel 'root_cause_analysis'): {e}")
            return False

    def _prepare_article_row(self, art: dict) -> dict:
        """Helper untuk normalisasi format data sebelum masuk DB."""
        url = art.get("url") or art.get("link", "")
        existing_id = art.get("id")
        if existing_id:
            row_id = str(existing_id)
        elif url:
            row_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url))
        else:
            row_id = str(uuid.uuid4())

        published_date = art.get("published_date") or art.get("waktu_tampilan")
        if hasattr(published_date, "isoformat"):
            published_date = published_date.isoformat()

        return {
            "id": row_id,
            "title": art.get("title") or art.get("judul"),
            "url": url,
            "source": art.get("source") or art.get("media"),
            "published_date": str(published_date) if published_date else None,
            "content": art.get("content") or art.get("isi_konten"),
            "sentiment": str(art.get("sentiment", art.get("Sentimen", "NEUTRAL"))).upper(),
            "keyword": art.get("keyword") or art.get("kata_kunci")
        }

db_service = DatabaseService()