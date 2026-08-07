"""
Scraper untuk postingan PUBLIK di Facebook (bukan profil pribadi, bukan
konten khusus teman/grup tertutup).

KENAPA PAKAI mbasic.facebook.com, BUKAN www.facebook.com:
Sempat diminta memakai XPath dari www.facebook.com (mis.
`//*[@id="mount_0_0_cM"]/div/div[1]/...`). Itu TIDAK dipakai di sini
dengan sengaja: `mount_0_0_cM` adalah id root React yang di-generate
ULANG SETIAP KALI HALAMAN DIMUAT (suffix-nya acak/berubah per sesi --
beda dengan id="dismissible" YouTube yang memang struktural/tetap). XPath
absolut yang menempel ke id semacam itu nyaris pasti langsung putus di
run berikutnya. www.facebook.com juga merender lewat React dengan
puluhan div bersarang & nama class yang di-obfuscate, jadi XPath sedalam
apa pun yang diambil dari satu momen tidak akan bertahan lama.

Solusinya: tetap pakai mbasic.facebook.com (versi HTML statis/ringan,
tanpa React, tanpa id acak, dan jauh lebih ramah untuk parsing) yang
memang sudah dipilih sejak awal karena alasan itu -- tapi PATTERN yang
diminta (content holder -> lalu ambil sumber/deskripsi/comment dari
dalamnya) tetap diikuti, hanya diterapkan ke markup mbasic yang lebih
stabil ini. `judul` tetap None sesuai permintaan (post Facebook memang
tidak punya field judul terpisah).

Facebook mendeteksi & memblokir automation dengan agresif dan sering
menampilkan dinding login bahkan untuk halaman publik biasa. Kalau
dinding login terdeteksi, scraper berhenti untuk target tsb dan
mengembalikan list kosong (tidak ada usaha bypass login/captcha).

CATATAN: markup mbasic di file ini didasarkan pada pola yang umum
didokumentasikan (elemen `data-ft`/`data-sigil`), belum diverifikasi
lewat run langsung di lingkungan ini (tidak ada akses jaringan di sandbox
pengembangan). Kemungkinan perlu sedikit disesuaikan begitu dites di
lingkungan Anda -- lihat catatan `_extract_comments` di bawah.
"""
import re
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.logger import get_logger
from app.services.social_scrapers.base import BaseSocialScraper

logger = get_logger("FacebookScraper")

MBASIC_BASE = "https://mbasic.facebook.com"
PERMALINK_MARKERS = ("/story.php", "/permalink.php", "story_fbid=", "/posts/")
MAX_COMMENTS_PER_POST = 15


class FacebookScraper(BaseSocialScraper):
    platform_name = "facebook"

    def _resolve_search_url(self, target: str) -> str:
        target = target.strip()
        if target.startswith("http"):
            path = urlparse(target).path.strip("/")
            return f"{MBASIC_BASE}/{path}"
        if target.startswith("@"):
            return f"{MBASIC_BASE}/{target.lstrip('@')}"
        return f"{MBASIC_BASE}/search/top/?q={quote(target)}"

    # -- tahap 1: kumpulkan content holder dari hasil pencarian ---------
    def _find_content_holders(self, soup: BeautifulSoup) -> List:
        return soup.select("div[data-ft]") or soup.select("article")

    def _extract_source(self, holder) -> str:
        """sumber: nama akun/halaman pemilik post -- dicoba dari <h3><a>
        dulu (pola paling umum di mbasic), fallback ke <strong><a> atau
        anchor pertama di dalam holder."""
        for selector in ("h3 a", "strong a", "a"):
            tag = holder.select_one(selector)
            if tag and tag.get_text(strip=True):
                return tag.get_text(strip=True)
        return ""

    def _extract_permalink(self, holder) -> Optional[str]:
        for a in holder.find_all("a", href=True):
            href = a["href"]
            if any(marker in href for marker in PERMALINK_MARKERS):
                return urljoin(MBASIC_BASE, href)
        first = holder.find("a", href=True)
        return urljoin(MBASIC_BASE, first["href"]) if first else None

    def _extract_description(self, holder, source_name: str) -> str:
        """deskripsi: teks isi post, dengan nama sumber (kalau berulang di
        awal), noise link "Lihat selengkapnya"/statistik jumlah komentar &
        share (sudah diambil terpisah oleh _extract_comment_count), dan
        link navigasi footer umum (Suka/Komentari/Bagikan, dst) disingkirkan
        supaya tidak ikut ke kolom deskripsi."""
        text = holder.get_text(" ", strip=True)
        if source_name and text.startswith(source_name):
            text = text[len(source_name):].strip(" ·-")

        text = re.sub(r"(Lihat selengkapnya|See [Mm]ore)", " ", text)
        text = re.sub(r"\d[\d.,]*\s*(Komentar|Comments?|Dibagikan|Shares?)", " ", text, flags=re.IGNORECASE)

        footer_markers = ["Suka", "Komentari", "Bagikan", "Like", "Comment", "Share"]
        cut_at = len(text)
        for marker in footer_markers:
            idx = text.find(marker)
            if idx != -1:
                cut_at = min(cut_at, idx)
        cleaned = text[:cut_at].strip()
        return re.sub(r"\s{2,}", " ", cleaned).strip(" ·-")

    def _extract_comment_count(self, holder) -> Optional[int]:
        text = holder.get_text(" ", strip=True)
        match = re.search(r"(\d[\d.,]*)\s*(Komentar|Comments?)", text, re.IGNORECASE)
        if not match:
            return None
        digits = re.sub(r"[^\d]", "", match.group(1))
        return int(digits) if digits else None

    # -- tahap 2: buka permalink post, ambil komentar --------------------
    def _extract_comments(self, permalink: str, max_comments: int = MAX_COMMENTS_PER_POST) -> List[str]:
        """mbasic menandai tiap elemen fungsional dengan atribut
        `data-sigil` (bukan class/id acak), termasuk komentar
        (`data-sigil="comment"`). Kalau markup mbasic berubah dan selector
        ini tidak lagi cocok, fallback-nya adalah pasangan <h3><a> (nama
        commenter) diikuti div teks -- pola umum baris komentar mbasic."""
        if not permalink or not self._safe_get(permalink):
            return []
        self._throttle()

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        if self._looks_like_login_wall(soup.get_text(" ", strip=True)):
            return []

        comment_nodes = soup.select('[data-sigil="comment"]')
        texts: List[str] = []

        if comment_nodes:
            for node in comment_nodes[:max_comments]:
                author = node.select_one("h3 a, strong a")
                author_name = author.get_text(strip=True) if author else ""
                body = node.get_text(" ", strip=True)
                if author_name and body.startswith(author_name):
                    body = body[len(author_name):].strip(" ·-")
                if body:
                    texts.append(f"{author_name}: {body}" if author_name else body)
        else:
            # Fallback heuristik kalau data-sigil tidak ditemukan.
            for h3 in soup.find_all("h3")[:max_comments]:
                author_tag = h3.find("a")
                if not author_tag:
                    continue
                body_tag = h3.find_next_sibling("div")
                body = body_tag.get_text(" ", strip=True) if body_tag else ""
                if body:
                    texts.append(f"{author_tag.get_text(strip=True)}: {body}")

        return texts

    def scrape(self, target: str, limit: int = 20) -> List[Dict]:
        url = self._resolve_search_url(target)
        posts: List[Dict] = []

        if not self._safe_get(url):
            return posts
        self._throttle()

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        if self._looks_like_login_wall(soup.get_text(" ", strip=True)):
            logger.warning(
                f"[facebook] Dinding login terdeteksi untuk '{target}'. "
                "Scraper ini tidak melakukan login otomatis; lewati target ini."
            )
            return posts

        holders = self._find_content_holders(soup)[:limit]
        for holder in holders:
            source_name = self._extract_source(holder)
            description = self._extract_description(holder, source_name)
            if not description or len(description) < 15:
                continue
            permalink = self._extract_permalink(holder) or url
            comment_count = self._extract_comment_count(holder)
            comment_texts = self._extract_comments(permalink)

            content_parts = [description]
            if comment_texts:
                numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(comment_texts, start=1))
                content_parts.append(f"--- Komentar Teratas ---\n{numbered}")

            posts.append({
                "platform": "facebook",
                "author": source_name or target,
                "content": "\n\n".join(content_parts)[:6000],
                "url": permalink,
                "posted_at": None,
                "likes": None,
                "comments": comment_count,
                "shares": None,
            })

        return posts
