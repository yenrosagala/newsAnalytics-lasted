import pandas as pd

def build_citation_index(df: pd.DataFrame) -> tuple[str, list[dict]]:
    """
    Membangun indeks sitasi dari dataframe berita dan menghasilkan 
    format teks korpus terindeks serta list metadata sitasi.
    """
    if df.empty:
        return "Tidak ada korpus berita yang tersedia.", []

    citation_list = []
    formatted_corpus_lines = []

    for index, row in df.iterrows():
        cite_id = index + 1
        title = row.get('title', 'Tanpa Judul')
        media = row.get('media', 'Media Tidak Diketahui')
        date = row.get('date', 'Tanggal Tidak Diketahui')
        content = row.get('content', row.get('snippet', ''))

        # Simpan struktur sitasi untuk referensi program/PDF
        citation_list.append({
            "id": cite_id,
            "title": title,
            "media": media,
            "date": date
        })

        # Format teks yang akan dibaca oleh LLM
        formatted_corpus_lines.append(
            f"[{cite_id}] Sumber: {media} | Tanggal: {date}\nJudul: {title}\nIsi: {content}\n"
        )

    concatenated_corpus = "\n".join(formatted_corpus_lines)
    return concatenated_corpus, citation_list