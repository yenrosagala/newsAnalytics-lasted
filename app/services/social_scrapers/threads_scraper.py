"""
Scraper untuk post + balasan PUBLIK di Threads (threads.net), platform
milik Meta.

ALUR 2 TAHAP:
1. Buka halaman profil/pencarian, kumpulkan "content holder" tiap post
   (`div[role="link"]` -- Threads belum dikonfirmasi punya atribut
   data-testid publik seperti X, jadi role="link" dipakai sebagai proxy:
   tiap post di feed Threads dibungkus elemen yang berperan sebagai link
   ke halaman detailnya sendiri).
2. Dari tiap holder, ambil permalink-nya (mengandung "/post/"), lalu
   KUNJUNGI halaman detail untuk membaca:
     - sumber    -> meta `og:title` (Threads mengisi og:title dengan nama
                     akun pembuat post -- lebih stabil daripada DOM
                     karena dipertahankan untuk keperluan link preview)
     - deskripsi -> meta `og:description` (isi post -- alasan sama
                     seperti dipakai di Instagram scraper: DOM Threads
                     berat & class-nya di-obfuscate, tapi meta tag
                     OpenGraph harus stabil untuk preview link)
     - comment   -> balasan yang tampil di bawah post utama di halaman
                     detail, diambil dengan content holder yang sama
                     (div[role="link"]) -- elemen ke-2 dst di halaman
                     detail = balasan, bukan post utama.

BATASAN PENTING (tidak berubah): Threads mengizinkan profil publik
dilihat tanpa login di browser biasa, tapi seperti Instagram/Facebook,
Meta bisa menampilkan dinding login kapan saja untuk traffic yang
terdeteksi sebagai automation. Scraper ini TIDAK melakukan login
otomatis -- kalau dinding login muncul, ia berhenti dan mengembalikan
apa pun yang sempat terkumpul (bisa kosong).
"""
from typing import Dict, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.core.logger import get_logger
from app.services.social_scrapers.base import BaseSocialScraper

logger = get_logger("ThreadsScraper")

POST_HOLDER_SELECTOR = "div[role='link']"
MAX_REPLIES_PER_POST = 15


class ThreadsScraper(BaseSocialScraper):
    platform_name = "threads"

    def _resolve_url(self, target: str) -> str:
        handle = target.strip().lstrip("@")
        if handle.startswith("http"):
            handle = handle.rstrip("/").split("/")[-1]
        if target.startswith("@") or "/" in handle:
            return f"https://www.threads.net/@{handle}"
        return f"https://www.threads.net/search/{quote(target)}"

    def _login_wall(self) -> bool:
        page_text = self.driver.find_element("tag name", "body").text
        return self._looks_like_login_wall(page_text)

    # -- tahap 1: kumpulkan permalink post dari content holder -----------
    def _collect_post_urls(self, limit: int) -> List[str]:
        self._scroll_to_load(scrolls=4, pause=1.5)
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        urls: List[str] = []
        seen = set()
        for node in soup.select(POST_HOLDER_SELECTOR):
            link_tag = node.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            post_url = href if href.startswith("http") else f"https://www.threads.net{href}"
            if post_url in seen or "/post/" not in post_url:
                continue
            seen.add(post_url)
            urls.append(post_url)
            if len(urls) >= limit:
                break
        return urls

    # -- tahap 2: buka tiap post, baca og:title/og:description + balasan --
    def _scrape_post_detail(self, url: str, fallback_author: str) -> Optional[Dict]:
        if not self._safe_get(url):
            return None
        self._throttle()

        if self._login_wall():
            logger.warning(f"[threads] Dinding login terdeteksi saat membuka {url}.")
            return None

        self._scroll_to_load(scrolls=2, pause=1.5)
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        title_meta = soup.find("meta", property="og:title")
        desc_meta = soup.find("meta", property="og:description")
        source_name = (
            title_meta["content"].strip() if title_meta and title_meta.get("content") else fallback_author
        )
        description = desc_meta["content"].strip() if desc_meta and desc_meta.get("content") else ""
        if not description:
            return None

        reply_texts: List[str] = []
        for node in soup.select(POST_HOLDER_SELECTOR)[1:1 + MAX_REPLIES_PER_POST]:
            text = node.get_text(" ", strip=True)
            if text and len(text) > 5 and text not in reply_texts:
                reply_texts.append(text[:500])

        content_parts = [description]
        if reply_texts:
            numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(reply_texts, start=1))
            content_parts.append(f"--- Balasan Teratas ---\n{numbered}")

        return {
            "platform": "threads",
            "author": source_name,
            "content": "\n\n".join(content_parts)[:6000],
            "url": url,
            "posted_at": None,
            "likes": None,
            "comments": len(reply_texts) if reply_texts else None,
            "shares": None,
        }

    def scrape(self, target: str, limit: int = 20) -> List[Dict]:
        handle = target.strip().lstrip("@")
        url = self._resolve_url(target)

        if not self._safe_get(url):
            return []
        self._throttle()

        if self._login_wall():
            logger.warning(
                f"[threads] Dinding login terdeteksi untuk '{handle}'. "
                "Scraper ini tidak melakukan login otomatis; lewati target ini."
            )
            return []

        post_urls = self._collect_post_urls(limit)
        if not post_urls:
            logger.warning(f"[threads] Tidak ada content holder ditemukan untuk '{handle}'.")
            return []

        results: List[Dict] = []
        for post_url in post_urls:
            detail = self._scrape_post_detail(post_url, fallback_author=handle)
            if detail:
                results.append(detail)
            self._throttle()

        return results
