"""
Orchestrator untuk semua scraper media sosial berbasis Selenium
(Facebook, Instagram, YouTube, Threads, X/Twitter).

Dipanggil dari app/api/endpoints/social_scraping.py, dan mengikuti pola
yang sama dengan ScraperService (app/services/scraper_service.py) supaya
konsisten dengan arsitektur yang sudah ada.

Lihat app/services/social_scrapers/base.py untuk batasan desain (hanya
konten publik, tanpa bypass login/captcha, rate-limited).
"""
from typing import Dict, List, Optional

from app.core.logger import get_logger
from app.services.database_service import db_service
from app.services.social_scrapers.facebook_scraper import FacebookScraper
from app.services.social_scrapers.instagram_scraper import InstagramScraper
from app.services.social_scrapers.threads_scraper import ThreadsScraper
from app.services.social_scrapers.twitter_scraper import TwitterScraper
from app.services.social_scrapers.youtube_scraper import YouTubeScraper

logger = get_logger("SocialScraperService")

SCRAPER_REGISTRY = {
    "facebook": FacebookScraper,
    "instagram": InstagramScraper,
    "youtube": YouTubeScraper,
    "threads": ThreadsScraper,
    "twitter": TwitterScraper,
    "x": TwitterScraper,  # alias
}

ALL_SOCIAL_PLATFORMS = [platform for platform in SCRAPER_REGISTRY.keys() if platform != "x"]


class SocialScraperService:
    """Service layer untuk menjalankan scraping media sosial & menyimpan hasilnya."""

    def execute_social_scraping_workflow(
        self,
        platform: str,
        target: str,
        limit: int = 20,
        keyword: Optional[str] = None,
        headless: bool = True,
        save_to_db: bool = True,
        status_container=None,
        progress_bar=None,
    ) -> Dict:
        """
        Jalankan scraping untuk satu platform + satu target, atau semua platform jika platform='all'.
        Simpan hasilnya ke database secara optional.

        target: tergantung platform -- bisa username/handle (mis. "@bbc"),
                URL profil/page publik, atau kata kunci pencarian
                (dipakai untuk YouTube/X search).
        """
        platform_key = (platform or "").lower().strip()
        if platform_key == "all":
            results = []
            total_posts: List[Dict] = []
            total_saved = 0
            platforms_count = len(ALL_SOCIAL_PLATFORMS)
            if status_container:
                status_container.info(f"Mulai scraping semua platform untuk target '{target}'...")
            if progress_bar:
                progress_bar.progress(0.05)

            for idx, platform_name in enumerate(ALL_SOCIAL_PLATFORMS, start=1):
                scraper_cls = SCRAPER_REGISTRY[platform_name]
                platform_posts: List[Dict] = []
                try:
                    if status_container:
                        status_container.info(f"Mengambil data dari {platform_name}...")
                    with scraper_cls(headless=headless) as scraper:
                        platform_posts = scraper.scrape(target=target, limit=limit)
                except Exception as e:
                    logger.error(f"[{platform_name}] Scraping gagal untuk target '{target}': {e}")
                    platform_posts = []

                for post in platform_posts:
                    post["keyword"] = keyword or target
                total_posts.extend(platform_posts)
                saved_count = 0
                if save_to_db and platform_posts:
                    saved_count = db_service.save_social_posts(platform_posts)
                    total_saved += saved_count
                results.append({
                    "platform": platform_name,
                    "target": target,
                    "fetched_count": len(platform_posts),
                    "saved_count": saved_count,
                    "posts": platform_posts,
                })

                if progress_bar:
                    progress_bar.progress(min(0.05 + 0.9 * (idx / platforms_count), 0.95))

            if status_container:
                status_container.success("Scraping semua platform selesai.")
            if progress_bar:
                progress_bar.progress(1.0)

            return {
                "platform": "all",
                "target": target,
                "fetched_count": len(total_posts),
                "saved_count": total_saved,
                "results": results,
                "posts": total_posts,
            }

        scraper_cls = SCRAPER_REGISTRY.get(platform_key)
        if not scraper_cls:
            supported = sorted({k for k in SCRAPER_REGISTRY if k != "x"}) + ["all"]
            raise ValueError(f"Platform '{platform}' tidak didukung. Pilihan: {supported}")
 
        posts: List[Dict] = []
        try:
            if status_container:
                status_container.info(f"Mengambil data dari {platform_key} untuk target '{target}'...")
            if progress_bar:
                progress_bar.progress(0.05)
            with scraper_cls(headless=headless) as scraper:
                posts = scraper.scrape(target=target, limit=limit)
        except Exception as e:
            logger.error(f"[{platform_key}] Scraping gagal untuk target '{target}': {e}")
            posts = []

        if status_container:
            status_container.success(f"Scraping {platform_key} selesai untuk target '{target}'.")
        if progress_bar:
            progress_bar.progress(1.0)

        for post in posts:
            post["keyword"] = keyword or target

        saved_count = 0
        if save_to_db and posts:
            saved_count = db_service.save_social_posts(posts)

        return {
            "platform": platform_key,
            "target": target,
            "fetched_count": len(posts),
            "saved_count": saved_count,
            "posts": posts,
        }


social_scraper_service = SocialScraperService()
