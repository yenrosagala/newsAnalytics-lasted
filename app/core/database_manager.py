# app/core/database_manager.py
import sqlite3
from contextlib import contextmanager
from app.core.config import get_config
from app.core.logger import setup_logger

logger = setup_logger("database_manager")
config = get_config()

class DatabaseManager:
    def __init__(self):
        self.db_path = config.DB_NAME
        self._init_db()

    def _init_db(self):
        """Memastikan tabel dasar terbentuk saat aplikasi pertama kali jalan."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Contoh pembuatan tabel berita jika belum ada
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_articles (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    source TEXT,
                    published_date TEXT,
                    content TEXT,
                    sentiment TEXT,
                    keyword TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logger.info("Database initialized successfully.")

    @contextmanager
    def get_connection(self):
        """Context manager untuk koneksi database yang aman."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Mengembalikan hasil query berupa dict-like object
        try:
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error occurred: {e}")
            conn.rollback()
            raise e
        finally:
            conn.close()

# Singleton instance agar tidak membuat banyak pool koneksi
db_manager = DatabaseManager()