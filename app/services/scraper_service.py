import time
import random
import xml.etree.ElementTree as ET
import requests
import concurrent.futures
from typing import Optional, List, Dict
import cloudscraper
from app.core.logger import get_logger
from app.services.ai_service import ai_service
from app.services.sentiment_service import sentiment_service
from app.services.database_service import db_service
from urllib.parse import urlparse

try:
    from newspaper import Config as NewspaperConfig
except ImportError:  # pragma: no cover - dependency guard
    NewspaperConfig = None

try:
    from googlenewsdecoder import gnewsdecoder
except ImportError:  # pragma: no cover - dependency guard
    gnewsdecoder = None

try:
    from newspaper import Article
except ImportError:  # pragma: no cover - dependency guard
    Article = None

logger = get_logger("ScraperService")

REGION_MAP = {
    "ID": ("id", "ID", "ID:id"),
    "US": ("en", "US", "US:en"),
}

MAX_SCRAPE_WORKERS = 10
ARTICLE_DOWNLOAD_TIMEOUT_SECONDS = 20
# 90s (dinaikkan dari 45s) -- 45s terlalu mepet: tiap artikel bisa butuh
# hingga ~2x ARTICLE_DOWNLOAD_TIMEOUT_SECONDS (2 percobaan newspaper4k) +
# GNEWS_DECODE_TIMEOUT_SECONDS, jadi batch timeout lama sering tercapai
# sebelum satu pun artikel selesai walau tidak ada error sungguhan -- cuma
# kelamaan, bukan macet total.
SCRAPE_BATCH_TIMEOUT_SECONDS = 90
# gnewsdecoder() sebelumnya dipanggil TANPA timeout keras sama sekali --
# kalau request ke Google lambat/macet, SEMUA item bisa menggantung
# bersamaan tanpa batas waktu individual, membuat seluruh batch timeout
# tercapai sebelum satu artikel pun selesai diproses (gejala "semuanya
# gagal diproses" walau RSS berhasil menemukan banyak entri). Timeout keras
# per-panggilan ini memastikan satu resolve URL yang macet tidak menahan
# thread selamanya.
GNEWS_DECODE_TIMEOUT_SECONDS = 10
# Jeda kecil SEBELUM tiap panggilan gnewsdecoder(). Nilai 0 (tanpa jeda)
# membuat puluhan permintaan decode menghantam endpoint Google News nyaris
# serentak -- Google lalu membalas gagal (status False) untuk SEMUA item
# dalam satu batch, sehingga semuanya jatuh ke fallback URL RSS mentah.
# Jeda ini berjalan di dalam tiap worker (tetap paralel), jadi burst-nya
# lebih rata tanpa memperlambat batch secara berarti.
GNEWS_DECODE_INTERVAL_SECONDS = 0.5
# Jumlah percobaan decode per URL + jeda backoff antar percobaan.
GNEWS_DECODE_ATTEMPTS = 3
GNEWS_DECODE_BACKOFF_SECONDS = 1.5

# Daftar user-agent alternatif untuk rotasi guna menghindari pembatasan/blokiran Cloudflare
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]


class ScraperService:
    """Service untuk menangani scraping berita dengan mekanisme pertahanan kegagalan tingkat lanjut."""

    def __init__(self) -> None:
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        self._newspaper_config = None
        if NewspaperConfig is not None:
            try:
                self._newspaper_config = NewspaperConfig()
                self._newspaper_config.request_timeout = ARTICLE_DOWNLOAD_TIMEOUT_SECONDS
                # Mengaktifkan pengabaian error fetch eksternal agar parser newspaper tetap mencoba membaca body
                self._newspaper_config.fetch_images = False
            except Exception as e:
                logger.warning(f"Gagal membuat newspaper4k Config kustom, pakai default library: {e}")
                self._newspaper_config = None

    def fetch_google_news_rss(self, keyword: str, region: str = "ID") -> str:
        """Mengambil data RSS feed dari Google News dengan retry & exponential backoff."""
        encoded_keyword = requests.utils.quote(keyword)
        hl, gl, ceid = REGION_MAP.get(region, REGION_MAP["ID"])
        url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl={hl}&gl={gl}&ceid={ceid}"
        
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # Rotasi header User-Agent acak di setiap percobaan
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                response = self.scraper.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                
                # Validasi konten apakah valid XML/RSS sebelum dikembalikan
                if "<rss" in response.text or "<item" in response.text:
                    return response.text
                logger.warning(f"Respons RSS Google News tidak valid pada percobaan ke-{attempt}")
            except requests.RequestException as e:
                logger.warning(f"Percobaan ke-{attempt} gagal fetch RSS untuk '{keyword}': {str(e)}")
                if attempt == max_retries:
                    logger.error(f"Gagal total fetch RSS untuk '{keyword}' setelah {max_retries} percobaan.")
                else:
                    time.sleep(2 ** attempt)  # Exponential backoff (2s, 4s)
        return ""

    def _resolve_real_url(self, google_url: str) -> str:
        """Menerjemahkan URL redirect Google News dengan mekanisme pengaman fallback.

        gnewsdecoder() adalah panggilan jaringan ke Google TANPA parameter
        timeout bawaan -- kalau macet, thread pemanggil bisa menggantung
        tanpa batas. Dibungkus lewat ThreadPoolExecutor + future.result()
        dengan GNEWS_DECODE_TIMEOUT_SECONDS supaya satu resolve yang macet
        tidak ikut menyeret seluruh batch scraping ke timeout global.
        """
        if not gnewsdecoder or not google_url:
            return google_url

        for attempt in range(GNEWS_DECODE_ATTEMPTS):
            # `with ThreadPoolExecutor(...)` sebelumnya TIDAK memberi timeout
            # nyata: __exit__ memanggil shutdown(wait=True) yang justru
            # menunggu thread menggantung, sehingga future.result(timeout=...)
            # tidak pernah membebaskan worker tepat waktu. shutdown eksplisit
            # dengan wait=False + cancel_futures=True memperbaiki itu.
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    gnewsdecoder, google_url, interval=GNEWS_DECODE_INTERVAL_SECONDS
                )
                result = future.result(timeout=GNEWS_DECODE_TIMEOUT_SECONDS)
                if result and result.get("status") and result.get("decoded_url"):
                    return result["decoded_url"]
                logger.warning(
                    f"Decode URL Google News ke-{attempt+1} tidak berhasil "
                    f"(status={result.get('status') if result else None}) untuk {google_url}."
                )
            except concurrent.futures.TimeoutError:
                logger.warning(
                    f"Decode URL Google News ke-{attempt+1} melewati batas waktu "
                    f"{GNEWS_DECODE_TIMEOUT_SECONDS}s untuk {google_url}."
                )
            except Exception as e:
                logger.warning(f"Percobaan decode URL Google News ke-{attempt+1} gagal: {e}")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            if attempt < GNEWS_DECODE_ATTEMPTS - 1:
                time.sleep(GNEWS_DECODE_BACKOFF_SECONDS * (attempt + 1))
        return google_url

    def _extract_article_metadata(self, url: str, fallback_title: str = "", fallback_desc: str = "") -> dict:
        """
        Mengambil metadata artikel dengan proteksi penuh terhadap hang, 
        invalid headers, SSL errors, atau blokiran situs berita target.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        media_name = domain.split('.')[0].capitalize() if domain else "Unknown"

        title = fallback_title
        publish_date = None
        authors = []
        full_text = fallback_desc

        if Article and url:
            for attempt in range(2):
                try:
                    article = Article(url, config=self._newspaper_config) if self._newspaper_config else Article(url)
                    
                    if hasattr(article, 'config') and article.config:
                        article.config.browser_user_agent = random.choice(USER_AGENTS)
                        # PERBAIKAN UTAMA: Nonaktifkan verifikasi SSL untuk mengatasi error sertifikat lokal
                        article.config.verify_ssl = False 
                    
                    article.download()
                    article.parse()

                    if article.title and len(article.title.strip()) > 5:
                        title = article.title.strip()
                    if article.publish_date:
                        publish_date = article.publish_date
                    if article.authors:
                        authors = article.authors
                    if article.text and len(article.text.strip()) > 100:
                        full_text = article.text.strip()
                        break  
                except Exception as e:
                    # Jika error karena SSL, kita bisa coba pakai cloudscraper session sebagai fallback unduhan
                    if "SSLError" in str(e) or "CERTIFICATE_VERIFY_FAILED" in str(e):
                        try:
                            logger.warning(f"SSL Error terdeteksi pada {url}, mencoba mengunduh via cloudscraper...")
                            response = self.scraper.get(url, timeout=15, verify=False)
                            if response.status_code == 200:
                                article.download_state = 2  # Tandai downloaded
                                article.html = response.text
                                article.parse()
                                if article.text and len(article.text.strip()) > 100:
                                    full_text = article.text.strip()
                                    if article.title:
                                        title = article.title.strip()
                                    break
                        except Exception as inner_e:
                            logger.warning(f"Fallback cloudscraper gagal: {inner_e}")

                    logger.warning(f"Gagal ekstrak artikel via newspaper4k (Percobaan {attempt+1}) dari {url}: {e}")
                    time.sleep(1)

        if not full_text or len(full_text.strip()) < 50:
            full_text = fallback_desc

        return {
            "media": media_name,
            "title": title,
            "publish_date": publish_date,
            "authors": authors,
            "content": full_text,
            "url": url
        }

    def _process_single_article(self, item: ET.Element, keyword: str) -> Optional[Dict]:
        """Memproses satu artikel secara aman dengan proteksi exception menyeluruh."""
        try:
            link = item.findtext('link')
            raw_title = item.findtext('title') or ""
            if not link:
                return None

            description = item.findtext('description') or ""
            real_url = self._resolve_real_url(link)
            
            meta = self._extract_article_metadata(real_url, fallback_title=raw_title, fallback_desc=description)

            sentiment_label = "NEUTRAL"
            try:
                if meta["content"]:
                    sentiment_label = sentiment_service.analyze_text(meta["content"])
            except Exception as sentiment_err:
                logger.warning(f"Analisis sentimen gagal untuk artikel {real_url}: {sentiment_err}")

            return {
                "title": meta["title"],
                "url": meta["url"],
                "source": meta["media"],
                "published_date": meta["publish_date"] or item.findtext('pubDate') or "",
                "authors": ", ".join(meta["authors"]) if meta["authors"] else "Unknown",
                "keyword": keyword,
                "content": meta["content"],
                "sentiment": sentiment_label,
            }
        except Exception as e:
            logger.warning(f"Gagal memproses item artikel: {str(e)}")
            return None

    def _process_items_concurrently(self, items: list, keyword: str, on_progress=None) -> List[Dict]:
        """Proses batch item RSS secara paralel dengan proteksi timeout batas batch."""
        total = len(items)
        articles: List[Dict] = []
        done = 0
        start = time.monotonic()

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SCRAPE_WORKERS)
        try:
            futures = {executor.submit(self._process_single_article, item, keyword): item for item in items}
            try:
                for future in concurrent.futures.as_completed(futures, timeout=SCRAPE_BATCH_TIMEOUT_SECONDS):
                    result = future.result()
                    done += 1
                    if result:
                        articles.append(result)
                    if on_progress:
                        on_progress(done, total, result)
            except concurrent.futures.TimeoutError:
                remaining = total - done
                logger.warning(
                    f"Batch scraping '{keyword}': batas waktu {SCRAPE_BATCH_TIMEOUT_SECONDS}s tercapai, "
                    f"{done}/{total} artikel selesai, {remaining} dilewati."
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        elapsed = time.monotonic() - start
        logger.info(
            f"Batch scraping '{keyword}' selesai dalam {elapsed:.1f}s: "
            f"{len(articles)}/{total} artikel berhasil diproses."
        )
        return articles

    def _fetch_and_process(self, keyword: str, limit: int, region: str) -> List[Dict]:
        xml_data = self.fetch_google_news_rss(keyword, region=region)
        if not xml_data:
            return []
        try:
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:limit]
        except ET.ParseError as e:
            logger.error(f"Gagal parsing XML RSS: {str(e)}")
            return []

        return self._process_items_concurrently(items, keyword)

    def fetch_articles_for_analysis(self, keyword: str, limit: int = 10, region: str = "ID") -> List[Dict]:
        return self._fetch_and_process(keyword, limit, region)

    def execute_scraping_workflow(
        self,
        keyword: str,
        limit: int = 10,
        region: str = "ID",
        status_container=None,
        progress_bar=None,
    ) -> Dict:
        empty_result = {"fetched_count": 0, "processed_count": 0, "saved_count": 0, "warning": None}

        if status_container:
            status_container.info(f"Mengambil daftar berita untuk '{keyword}'...")
        if progress_bar:
            progress_bar.progress(0.1)

        xml_data = self.fetch_google_news_rss(keyword, region=region)
        if not xml_data:
            warning = f"Tidak ada respons dari Google News RSS untuk keyword '{keyword}'."
            logger.warning(warning)
            if status_container:
                status_container.warning(warning)
            return {**empty_result, "warning": warning}

        try:
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:limit]
        except ET.ParseError as e:
            warning = f"Gagal membaca format RSS dari Google News untuk '{keyword}': {e}"
            logger.error(warning)
            if status_container:
                status_container.error(warning)
            return {**empty_result, "warning": warning}

        if not items:
            warning = f"Google News tidak mengembalikan artikel apa pun untuk keyword '{keyword}'."
            logger.warning(warning)
            if status_container:
                status_container.warning(warning)
            return {**empty_result, "warning": warning}

        total = len(items)

        def _on_progress(done, total_, result):
            if progress_bar:
                progress_bar.progress(min(0.1 + 0.8 * (done / total_), 0.9))
            if result and status_container:
                status_container.text(f"Memproses ({done}/{total_}): {result['title'][:70]}...")

        articles = self._process_items_concurrently(items, keyword, on_progress=_on_progress)

        if not articles:
            warning = f"Google News menemukan {total} entri untuk '{keyword}', tapi semuanya gagal diproses."
            logger.warning(warning)
            if status_container:
                status_container.warning(warning)
            return {**empty_result, "fetched_count": total, "warning": warning}

        try:
            saved_count = db_service.save_articles(articles)
        except Exception as db_err:
            logger.error(f"Gagal menyimpan artikel ke database: {db_err}")
            saved_count = 0

        if progress_bar:
            progress_bar.progress(1.0)

        warning = None
        if saved_count == 0:
            warning = f"{len(articles)} artikel berhasil diproses untuk '{keyword}', tapi 0 tersimpan sebagai baru (kemungkinan duplikat URL)."
            logger.info(warning)
            if status_container:
                status_container.warning(warning)

        return {
            "fetched_count": total,
            "processed_count": len(articles),
            "saved_count": saved_count,
            "warning": warning,
        }


scraper_service = ScraperService()