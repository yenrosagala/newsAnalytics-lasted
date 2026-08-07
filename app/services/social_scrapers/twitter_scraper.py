"""
Scraper untuk post PUBLIK di X (Twitter).

ALUR 2 TAHAP (sama seperti YouTube/Facebook):
1. Buka halaman pencarian/profil, kumpulkan "content holder" tiap tweet
   (`article[data-testid="tweet"]` -- atribut data-testid ini milik X
   sendiri untuk keperluan testing internal mereka, jadi jauh lebih
   stabil dibanding class name yang di-obfuscate & berubah tiap build).
2. Dari tiap holder, ambil permalink tweet-nya (.../status/<id>), lalu
   KUNJUNGI halaman detailnya untuk mengambil:
     - sumber    -> div[data-testid="User-Name"] (nama tampilan + @handle)
     - deskripsi -> div[data-testid="tweetText"] (teks tweet utama, versi
                     lengkap tanpa terpotong seperti yang tampil di feed)
     - comment   -> balasan yang tampil di bawah tweet utama di halaman
                     detail -- tiap balasan juga dirender sebagai
                     article[data-testid="tweet"], jadi elemen ke-2 dst
                     di halaman detail = balasan (bukan tweet utama).

CATATAN: jumlah balasan di kolom `comments` adalah jumlah balasan yang
BERHASIL DIMUAT & diambil (dibatasi MAX_REPLIES_PER_TWEET), bukan angka
resmi total balasan dari X -- X tidak menampilkan angka itu di DOM tanpa
API resmi.

BATASAN PENTING (tidak berubah): sejak kebijakan X berubah (2023 dst), X
menampilkan dinding login untuk hampir SEMUA traffic tanpa sesi login,
termasuk banyak profil publik & hasil pencarian, dalam waktu singkat
setelah halaman dibuka. Scraper ini TIDAK melakukan login otomatis --
begitu dinding login terdeteksi, target itu dilewati (list kosong). Ini
batasan platform, bukan bug kode ini. Untuk kebutuhan yang andal,
pertimbangkan X API resmi (berbayar) atau sumber data pihak ketiga yang
berlisensi resmi dari X.
"""
from typing import Dict, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.core.logger import get_logger
from app.services.social_scrapers.base import BaseSocialScraper

logger = get_logger("TwitterScraper")

TWEET_HOLDER_SELECTOR = "article[data-testid='tweet']"
TWEET_TEXT_SELECTOR = "div[data-testid='tweetText']"
USER_NAME_SELECTOR = "div[data-testid='User-Name']"
MAX_REPLIES_PER_TWEET = 15


class TwitterScraper(BaseSocialScraper):
    platform_name = "twitter"

    def _resolve_url(self, target: str) -> str:
        target = target.strip()
        if target.startswith("http"):
            return target
        if target.startswith("@"):
            return f"https://x.com/{target.lstrip('@')}"
        return f"https://x.com/search?q={quote(target)}&f=live"

    def _login_wall(self) -> bool:
        page_text = self.driver.find_element("tag name", "body").text
        return self._looks_like_login_wall(page_text)

    # -- tahap 1: kumpulkan permalink tweet dari content holder ----------
    def _collect_tweet_urls(self, limit: int) -> List[str]:
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        urls: List[str] = []
        seen = set()
        for article in soup.select(TWEET_HOLDER_SELECTOR):
            link_tag = article.find("a", href=True, attrs={"href": lambda h: h and "/status/" in h})
            if not link_tag:
                continue
            href = link_tag["href"]
            post_url = href if href.startswith("http") else f"https://x.com{href}"
            if post_url in seen:
                continue
            seen.add(post_url)
            urls.append(post_url)
            if len(urls) >= limit:
                break
        return urls

    # -- tahap 2: buka tiap tweet, ambil sumber/deskripsi/balasan --------
    def _scrape_tweet_detail(self, url: str, fallback_author: str) -> Optional[Dict]:
        if not self._safe_get(url):
            return None
        self._throttle()

        if self._login_wall():
            logger.warning(f"[twitter] Dinding login terdeteksi saat membuka {url}.")
            return None

        self._scroll_to_load(scrolls=2, pause=1.5)
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        holders = soup.select(TWEET_HOLDER_SELECTOR)
        if not holders:
            return None

        main = holders[0]
        text_node = main.select_one(TWEET_TEXT_SELECTOR)
        description = text_node.get_text(" ", strip=True) if text_node else ""
        if not description:
            return None

        name_node = main.select_one(USER_NAME_SELECTOR)
        source_name = name_node.get_text(" ", strip=True) if name_node else fallback_author

        reply_texts = []
        for reply_article in holders[1:1 + MAX_REPLIES_PER_TWEET]:
            reply_text_node = reply_article.select_one(TWEET_TEXT_SELECTOR)
            reply_text = reply_text_node.get_text(" ", strip=True) if reply_text_node else ""
            if not reply_text:
                continue
            reply_author_node = reply_article.select_one(USER_NAME_SELECTOR)
            reply_author = reply_author_node.get_text(" ", strip=True) if reply_author_node else ""
            reply_texts.append(f"{reply_author}: {reply_text}" if reply_author else reply_text)

        content_parts = [description]
        if reply_texts:
            numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(reply_texts, start=1))
            content_parts.append(f"--- Balasan Teratas ---\n{numbered}")

        return {
            "platform": "twitter",
            "author": source_name,
            "content": "\n\n".join(content_parts)[:6000],
            "url": url,
            "posted_at": None,
            "likes": None,
            "comments": len(reply_texts) if reply_texts else None,
            "shares": None,
        }

    def scrape(self, target: str, limit: int = 20) -> List[Dict]:
        url = self._resolve_url(target)
        if not self._safe_get(url):
            return []
        self._throttle()

        if self._login_wall():
            logger.warning(
                f"[twitter] Dinding login terdeteksi untuk '{target}'. X sering "
                "menampilkan ini untuk traffic tanpa sesi login; scraper tidak "
                "melakukan login otomatis, jadi target ini dilewati."
            )
            return []

        self._scroll_to_load(scrolls=4, pause=1.5)
        tweet_urls = self._collect_tweet_urls(limit)
        if not tweet_urls:
            logger.warning(f"[twitter] Tidak ada content holder (tweet) ditemukan untuk '{target}'.")
            return []

        results: List[Dict] = []
        for tweet_url in tweet_urls:
            detail = self._scrape_tweet_detail(tweet_url, fallback_author=target)
            if detail:
                results.append(detail)
            self._throttle()

        return results
