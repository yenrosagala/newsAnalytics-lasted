# app/repositories/news_repository.py
from typing import List, Dict, Any
from app.core.database_manager import db_manager
from app.core.logger import setup_logger

logger = setup_logger("news_repository")

class NewsRepository:
    @staticmethod
    def save_articles(articles: List[Dict[str, Any]]):
        """Menyimpan banyak artikel sekaligus menggunakan execute many (bulk insert)."""
        query = """
            INSERT OR IGNORE INTO news_articles (id, title, url, source, published_date, content, sentiment, keyword)
            VALUES (:id, :title, :url, :source, :published_date, :content, :sentiment, :keyword)
        """
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, articles)
                conn.commit()
                logger.info(f"Successfully saved {cursor.rowcount} new articles.")
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to save articles: {e}")
            return 0

    @staticmethod
    def get_articles_by_keyword(keyword: str) -> List[Dict[str, Any]]:
        """Mengambil data artikel berdasarkan keyword."""
        query = "SELECT * FROM news_articles WHERE keyword = ? ORDER BY published_date DESC"
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (keyword,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch articles for keyword '{keyword}': {e}")
            return []

    @staticmethod
    def get_sentiment_stats(keyword: str) -> Dict[str, int]:
        """Mengambil ringkasan statistik sentiment untuk dashboard."""
        query = """
            SELECT sentiment, COUNT(*) as count 
            FROM news_articles 
            WHERE keyword = ? 
            GROUP BY sentiment
        """
        stats = {"Positive": 0, "Negative": 0, "Neutral": 0}
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (keyword,))
                for row in cursor.fetchall():
                    sentiment_label = row["sentiment"]
                    if sentiment_label in stats:
                        stats[sentiment_label] = row["count"]
            return stats
        except Exception as e:
            logger.error(f"Failed to fetch sentiment stats: {e}")
            return stats