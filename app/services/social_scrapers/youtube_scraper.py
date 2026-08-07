"""
Scraper untuk video PUBLIK di YouTube: hasil pencarian atau daftar video
sebuah channel. Tidak memerlukan login untuk konten publik biasa.

ALUR 2 TAHAP (sesuai permintaan):
1. Buka halaman pencarian, kumpulkan "content holder" tiap hasil video
   (`id="dismissible"` -- ini id struktural bawaan komponen
   `ytd-video-renderer`/`ytd-rich-item-renderer` milik YouTube, dipakai
   berulang untuk SETIAP item hasil, bukan id acak per-sesi seperti punya
   Facebook -- jadi relatif aman dipakai lewat XPath meskipun secara HTML
   murni id seharusnya unik).
2. Dari tiap holder, ambil link videonya lalu KUNJUNGI halaman detail
   videonya satu per satu untuk mengambil:
     - judul       -> //*[@id="title"]/h1
     - sumber      -> //*[@id="text"]/a   (nama channel)
     - description -> //*[@id="description"]
     - comment     -> //*[@id="contents"] (container komentar, di-scroll
                       dulu supaya komentar ke-lazy-load, lalu tiap
                       komentar individual diambil teksnya)

CATATAN SKEMA: kolom `comments` di database bertipe angka (jumlah
komentar), BUKAN teks -- lihat supabase_migration_social_posts.sql. Jadi
isi komentar (teks) digabung ke dalam `content` (di bagian bawah, diberi
label jelas), sedangkan `comments` diisi angka jumlah komentar kalau
berhasil terbaca dari halaman, atau None kalau tidak.

CATATAN API RESMI: YouTube Data API v3 jauh lebih stabil & punya kuota
gratis harian. Scraper Selenium di sini dipakai untuk konsistensi dengan
platform lain, tapi kalau butuh keandalan produksi, API resmi lebih
direkomendasikan.
"""
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.core.logger import get_logger
from app.services.social_scrapers.base import BaseSocialScraper

logger = get_logger("YouTubeScraper")

RESULT_HOLDER_XPATH = "//*[@id='dismissible']"
TITLE_XPATH = "//*[@id='title']/h1"
CHANNEL_XPATH = "//*[@id='text']/a"
DESCRIPTION_XPATH = "//*[@id='description']"
COMMENTS_CONTAINER_XPATH = "//*[@id='contents']"
COMMENT_COUNT_XPATH = "//*[@id='count']//yt-formatted-string"

MAX_COMMENTS_PER_VIDEO = 15


class YouTubeScraper(BaseSocialScraper):
    platform_name = "youtube"

    def _resolve_search_url(self, target: str) -> str:
        target = target.strip()
        if target.startswith("http"):
            return target
        if target.startswith("@"):
            return f"https://www.youtube.com/{target}/videos"
        # Diperlakukan sebagai kata kunci pencarian
        return f"https://www.youtube.com/results?search_query={quote(target)}"

    # -- tahap 1: kumpulkan URL video dari tiap content holder ----------
    def _collect_result_urls(self, limit: int) -> List[str]:
        urls: List[str] = []
        seen = set()
        holders = self.driver.find_elements(By.XPATH, RESULT_HOLDER_XPATH)
        for holder in holders:
            try:
                link = holder.find_element(By.XPATH, ".//a[contains(@href,'/watch?v=')]")
                href = link.get_attribute("href")
            except NoSuchElementException:
                continue
            if not href or href in seen:
                continue
            seen.add(href)
            urls.append(href)
            if len(urls) >= limit:
                break
        return urls

    # -- tahap 2: buka tiap video, ambil judul/sumber/deskripsi/komentar --
    def _extract_comment_count(self) -> Optional[int]:
        try:
            text = self.driver.find_element(By.XPATH, COMMENT_COUNT_XPATH).text
            digits = re.sub(r"[^\d]", "", text)
            return int(digits) if digits else None
        except (NoSuchElementException, ValueError):
            return None

    def _extract_comments(self, max_comments: int = MAX_COMMENTS_PER_VIDEO) -> List[str]:
        """Komentar di-lazy-load saat halaman discroll. Scroll dulu ke area
        komentar, tunggu container-nya muncul, baru ambil teks tiap komentar."""
        texts: List[str] = []
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
            time.sleep(1.5)
            self._scroll_to_load(scrolls=3, pause=1.5)
            container = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, COMMENTS_CONTAINER_XPATH))
            )
            nodes = container.find_elements(By.CSS_SELECTOR, "#content-text")
            for node in nodes[:max_comments]:
                text = node.text.strip()
                if text:
                    texts.append(text)
        except TimeoutException:
            logger.debug("[youtube] Komentar tidak dimuat (mungkin dimatikan untuk video ini).")
        except Exception as e:
            logger.debug(f"[youtube] Gagal mengambil komentar: {e}")
        return texts

    def _scrape_video_detail(self, url: str, fallback_author: str) -> Optional[Dict]:
        if not self._safe_get(url):
            return None
        self._throttle()

        try:
            title = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, TITLE_XPATH))
            ).text.strip()
        except TimeoutException:
            title = ""

        try:
            channel_name = self.driver.find_element(By.XPATH, CHANNEL_XPATH).text.strip()
        except NoSuchElementException:
            channel_name = ""

        try:
            description = self.driver.find_element(By.XPATH, DESCRIPTION_XPATH).text.strip()
        except NoSuchElementException:
            description = ""

        comment_count = self._extract_comment_count()
        comment_texts = self._extract_comments()

        if not title and not description:
            return None

        parts = []
        if title:
            parts.append(title)
        if description:
            parts.append(description)
        if comment_texts:
            numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(comment_texts, start=1))
            parts.append(f"--- Komentar Teratas ---\n{numbered}")
        content = "\n\n".join(parts)[:6000]

        return {
            "platform": "youtube",
            "author": channel_name or fallback_author,
            "content": content,
            "url": url,
            "posted_at": None,
            "likes": None,
            "comments": comment_count,
            "shares": None,
        }

    def scrape(self, target: str, limit: int = 20) -> List[Dict]:
        search_url = self._resolve_search_url(target)
        if not self._safe_get(search_url):
            return []
        self._throttle()
        self._scroll_to_load(scrolls=4, pause=1.5)

        video_urls = self._collect_result_urls(limit)
        if not video_urls:
            logger.warning(f"[youtube] Tidak ada content holder (id='dismissible') ditemukan untuk '{target}'.")
            return []

        results: List[Dict] = []
        for url in video_urls:
            detail = self._scrape_video_detail(url, fallback_author=target)
            if detail:
                results.append(detail)
            self._throttle()

        return results
