"""
Sub-paket scraper media sosial berbasis Selenium.

Setiap platform punya class scraper sendiri (lihat base.py untuk kontrak
bersama). Orkestrasinya ada di app/services/social_scraper_service.py.

BACA app/services/social_scrapers/README_LIMITATIONS.md sebelum dipakai
di production -- ada batasan penting soal ToS platform dan stabilitas
selector yang wajib dipahami.
"""
from app.services.social_scrapers.facebook_scraper import FacebookScraper
from app.services.social_scrapers.instagram_scraper import InstagramScraper
from app.services.social_scrapers.youtube_scraper import YouTubeScraper
from app.services.social_scrapers.threads_scraper import ThreadsScraper
from app.services.social_scrapers.twitter_scraper import TwitterScraper

__all__ = [
    "FacebookScraper",
    "InstagramScraper",
    "YouTubeScraper",
    "ThreadsScraper",
    "TwitterScraper",
]
