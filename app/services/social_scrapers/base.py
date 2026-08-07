"""
Base class untuk semua scraper media sosial berbasis Selenium.

DESAIN & BATASAN (baca sebelum pakai):
- Hanya mengakses halaman PUBLIK. Class ini TIDAK melakukan login otomatis,
  tidak menyimpan/mengetik kredensial, dan tidak berusaha melewati captcha
  atau proteksi anti-bot. Kalau target memerlukan login, scraper akan
  mendeteksi dinding login dan berhenti (mengembalikan list kosong) untuk
  target tsb, bukan mencoba menerobosnya.
- Ada jeda acak (rate limit) antar-request untuk mengurangi beban ke
  server platform dan risiko pemblokiran IP/akun.
- Facebook, Instagram, Threads, dan X/Twitter melarang scraping otomatis
  di Terms of Service masing-masing. Modul ini disediakan untuk riset,
  monitoring media, atau data milik/di-otorisasi sendiri -- tanggung jawab
  kepatuhan ToS & hukum (mis. GDPR/UU PDP soal data pribadi) ada di
  pemakai. Untuk kebutuhan produksi/skala besar, gunakan API resmi
  platform (mis. YouTube Data API, Meta Graph API) jika tersedia.
- Struktur HTML platform-platform ini berubah cukup sering. Selector di
  tiap scraper adalah titik awal yang perlu dipelihara/disesuaikan
  berkala, bukan solusi permanen.
"""
import random
import time
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from app.core.logger import get_logger

logger = get_logger("SocialScraperBase")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class BaseSocialScraper:
    """Kontrak bersama: setiap platform scraper harus implement `scrape()`."""

    platform_name = "base"

    def __init__(
        self,
        headless: bool = True,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        page_load_timeout: int = 25,
        user_agent: Optional[str] = None,
    ):
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.page_load_timeout = page_load_timeout
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.driver = None

    # -- lifecycle ---------------------------------------------------
    def _build_options(self) -> Options:
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1366,900")
        options.add_argument("--lang=en-US")
        options.add_argument(f"user-agent={self.user_agent}")
        # Mengurangi noise & sedikit menyamarkan automation flag standar
        # (bukan bypass anti-bot, cuma preferensi umum agar rendering lebih
        # konsisten dengan browser biasa).
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return options

    def start(self) -> "webdriver.Chrome":
        if self.driver:
            return self.driver
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=self._build_options())
            self.driver.set_page_load_timeout(self.page_load_timeout)
        except WebDriverException as e:
            logger.error(f"[{self.platform_name}] Gagal menjalankan Chrome WebDriver: {e}")
            raise
        return self.driver

    def stop(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def __enter__(self) -> "BaseSocialScraper":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # -- helpers -------------------------------------------------------
    def _throttle(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def _safe_get(self, url: str) -> bool:
        try:
            self.driver.get(url)
            return True
        except TimeoutException:
            logger.warning(f"[{self.platform_name}] Timeout membuka {url}")
            return False
        except WebDriverException as e:
            logger.warning(f"[{self.platform_name}] Gagal membuka {url}: {e}")
            return False

    def _wait_for(self, by, selector: str, timeout: int = 10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except TimeoutException:
            return None

    def _scroll_to_load(self, scrolls: int = 5, pause: float = 1.5) -> None:
        """Scroll halaman untuk memicu lazy-load / infinite scroll."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        for _ in range(scrolls):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def _looks_like_login_wall(self, page_text: str) -> bool:
        markers = [
            "log in to", "log into", "login to see", "you must log in",
            "sign in to", "masuk untuk", "masuk ke akun", "log in or sign up",
        ]
        lowered = page_text.lower()
        return any(m in lowered for m in markers)

    # -- contract --------------------------------------------------
    def scrape(self, target: str, limit: int = 20) -> List[Dict]:
        """
        Ambil post publik terbaru dari `target` (username/handle/URL/kata
        kunci, tergantung platform), maksimal `limit` item.

        Return: list of dict dengan key minimal:
            platform, author, content, url, posted_at, likes, comments, shares
        """
        raise NotImplementedError
