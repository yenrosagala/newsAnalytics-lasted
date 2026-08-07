import logging
import sys

log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Inisialisasi konfigurasi dasar root logger
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

def get_logger(name: str):
    """Mengembalikan logger instance berdasarkan nama modul."""
    return logging.getLogger(name)

def setup_logger(name: str = "AppLogger", *args, **kwargs):
    """
    Fungsi pembungkus dinamis. 
    Bisa dipanggil tanpa argumen: setup_logger()
    Atau dengan argumen posisi: setup_logger(__name__)
    """
    return logging.getLogger(name)

# Sediakan objek logger default langsung
logger = logging.getLogger("AppLogger")