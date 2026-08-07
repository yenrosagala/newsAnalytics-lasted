import pandas as pd
from app.services.metadata_builder import build_metadata
from app.services.citation_builder import build_citation_index
from app.ai.system_prompt import SYSTEM_PROMPT # Sesuaikan path prompt Anda

def generate_report_payload(df: pd.DataFrame, keyword: str):
    # 1. Buat Metadata secara deterministik via Python
    metadata = build_metadata(df, keyword)
    
    # 2. Buat Citation Index dan Korpus Terindeks
    corpus_text, citations = build_citation_index(df)
    
    # 3. Susun User Prompt yang ringkas (tanpa logika berbelit-belit di prompt)
    user_prompt = f"""
    Metadata Laporan:
    - Keyword: {metadata['keyword']}
    - Total Artikel: {metadata['total_articles']}
    - Rentang Tanggal: {metadata['date_range']['start']} sampai {metadata['date_range']['end']}
    - Media Dominan: {metadata['top_media']}

    Korpus Berita Terindeks:
    {corpus_text}
    """
    
    # 4. Payload siap dikirim ke LLM (mendukung system & user role)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    
    return messages, citations