"""
Scraper untuk caption + jumlah komentar post PUBLIK di profil Instagram.

ALUR 2 TAHAP:
1. Buka halaman profil/hashtag, kumpulkan link tiap post (`/p/...` atau
   `/reel/...`) dari grid sebagai daftar "content holder" -- Instagram
   tidak merender caption per-post di halaman grid itu sendiri, hanya
   thumbnail + link, jadi tahap ini murni mengumpulkan URL untuk
   dikunjungi satu per satu di tahap 2.
2. KUNJUNGI tiap post, lalu baca meta tag `og:description` di <head>.
   Ini pilihan yang sengaja diambil: DOM Instagram memakai class name
   acak yang di-obfuscate & berubah tiap build, sedangkan meta tag
   OpenGraph relatif stabil karena Instagram butuh itu supaya link-nya
   bisa di-preview dengan benar di WhatsApp/Facebook/dst. Formatnya
   konsisten: `"{likes} likes, {comments} comments - {username} on
   {date}: \"{caption}\""` -- sumber, deskripsi (caption), dan jumlah
   komentar diambil dari sini lewat regex, bukan dari DOM.

BATASAN PENTING (tidak berubah): sejak beberapa tahun terakhir Instagram
menampilkan dinding login untuk hampir semua traffic non-login, termasuk
saat membuka detail post satu per satu. Scraper ini TIDAK melakukan
login otomatis -- begitu dinding login terdeteksi, sisa proses untuk
target itu dihentikan dan apa pun yang sempat terkumpul dikembalikan
(bisa kosong). Ini batasan platform, bukan bug kode ini.

Isi TEKS tiap komentar (bukan sekadar jumlahnya) sengaja TIDAK diambil
dari DOM di sini -- itu perlu scroll & render JS yang hampir selalu
memicu dinding login lebih dulu dibanding caption+meta yang sudah ada di
initial HTML. Kalau butuh isi komentar sungguhan, pertimbangkan
Instagram Graph API resmi dari Meta (perlu izin akun/business).
"""
import re
from typing import Dict, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.core.logger import get_logger
from app.services.social_scrapers.base import BaseSocialScraper

logger = get_logger("InstagramScraper")

OG_DESC_PATTERN = re.compile(
    r"([\d.,KMkm]+)\s*likes?,\s*([\d.,KMkm]+)\s*comments?\s*-\s*(.+?)\s*on\s*(.+?):\s*\"(.*)\"",
    re.IGNORECASE | re.DOTALL,
)


class InstagramScraper(BaseSocialScraper):
    platform_name = "instagram"

    def _resolve_url(self, target: str) -> str:
        handle = target.strip().lstrip("@#")
        if handle.startswith("http"):
            handle = handle.rstrip("/").split("/")[-1]
        if " " in handle or target.startswith("#"):
            return f"https://www.instagram.com/explore/tags/{quote(handle)}/"
        return f"https://www.instagram.com/{handle}/"

    def _login_wall(self) -> bool:
        page_text = self.driver.find_element("tag name", "body").text
        return self._looks_like_login_wall(page_text)

    @staticmethod
    def _parse_count(raw: str) -> Optional[int]:
        raw = raw.strip().upper().replace(",", "")
        try:
            if raw.endswith("K"):
                return int(float(raw[:-1]) * 1_000)
            if raw.endswith("M"):
                return int(float(raw[:-1]) * 1_000_000)
            return int(float(raw))
        except ValueError:
            return None

    # -- tahap 1: kumpulkan link post dari grid profil/hashtag ----------
    def _collect_post_urls(self, limit: int) -> List[str]:
        self._scroll_to_load(scrolls=3, pause=1.5)
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        urls: List[str] = []
        seen = set()
        for a in soup.select("a[href*='/p/'], a[href*='/reel/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)
            urls.append(href if href.startswith("http") else f"https://www.instagram.com{href}")
            if len(urls) >= limit:
                break
        return urls

    # -- tahap 2: buka tiap post, baca og:description --------------------
    def _scrape_post_detail(self, url: str, fallback_author: str) -> Optional[Dict]:
        if not self._safe_get(url):
            return None
        self._throttle()

        if self._login_wall():
            logger.warning(f"[instagram] Dinding login terdeteksi saat membuka {url}.")
            return None

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        meta = soup.find("meta", property="og:description")
        raw = meta["content"] if meta and meta.get("content") else ""
        if not raw:
            return None

        match = OG_DESC_PATTERN.search(raw)
        if match:
            _like_raw, comment_raw, username, _date, caption = match.groups()
            comment_count = self._parse_count(comment_raw)
            source_name = username.strip() or fallback_author
            caption = caption.strip()
        else:
            comment_count = None
            source_name = fallback_author
            caption = raw.strip()

        if not caption:
            return None

        return {
            "platform": "instagram",
            "author": source_name,
            "content": caption[:6000],
            "url": url,
            "posted_at": None,
            "likes": None,
            "comments": comment_count,
            "shares": None,
        }

    def scrape(self, target: str, limit: int = 20) -> List[Dict]:
        handle = target.strip().lstrip("@#")
        url = self._resolve_url(target)

        if not self._safe_get(url):
            return []
        self._throttle()

        if self._login_wall():
            logger.warning(
                f"[instagram] Dinding login terdeteksi untuk '{handle}'. "
                "Scraper ini tidak melakukan login otomatis; lewati target ini."
            )
            return []

        post_urls = self._collect_post_urls(limit)
        if not post_urls:
            logger.warning(f"[instagram] Tidak ada link post ditemukan untuk '{handle}'.")
            return []

        results: List[Dict] = []
        for post_url in post_urls:
            detail = self._scrape_post_detail(post_url, fallback_author=handle)
            if detail:
                results.append(detail)
            self._throttle()

        return results
