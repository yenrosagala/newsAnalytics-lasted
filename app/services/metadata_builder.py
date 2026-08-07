from datetime import datetime
import pandas as pd

def build_metadata(df: pd.DataFrame, keyword: str) -> dict:
    """
    Membangun metadata terstruktur dari dataframe berita hasil scraping.
    """
    if df.empty:
        return {
            "keyword": keyword,
            "total_articles": 0,
            "date_range": {"start": None, "end": None},
            "top_media": []
        }

    # Memastikan kolom tanggal bertipe datetime jika ada
    if 'date' in df.columns:
        dates = pd.to_datetime(df['date'], errors='coerce')
        start_date = dates.min().strftime('%Y-%m-%d') if not dates.dropna().empty else "Unknown"
        end_date = dates.max().strftime('%Y-%m-%d') if not dates.dropna().empty else "Unknown"
    else:
        start_date, end_date = "Unknown", "Unknown"

    # Menghitung media dominan (top media)
    top_media = []
    if 'media' in df.columns:
        media_counts = df['media'].value_counts().head(5)
        top_media = [{"media": media, "count": int(count)} for media, count in media_counts.items()]

    metadata = {
        "keyword": keyword,
        "total_articles": len(df),
        "date_range": {
            "start": start_date,
            "end": end_date
        },
        "top_media": top_media,
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    return metadata