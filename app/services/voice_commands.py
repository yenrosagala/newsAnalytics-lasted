"""Parser perintah suara Jarvis (murni Python, tanpa I/O) -- memetakan teks
hasil pengenalan suara browser ke aksi aplikasi.

Sengaja dipisah dari komponen Streamlit supaya bisa diuji tanpa menjalankan
server (lihat self-check di bawah), dan supaya aturan bahasa Indonesia tidak
tercampur dengan kode UI. Cakupan sengaja sempit: navigasi antar-modul dan
"analisis <topik>". Perintah di luar itu diperlakukan sebagai pertanyaan bebas
(type "question") -- pemanggil yang memutuskan mau diapakan.
"""
import re

# Hapus tanda baca supaya "Buka Dashboard." == "buka dashboard".
_PUNCT_RE = re.compile(r"[^\w\s]")
_ANALYZE_RE = re.compile(r"^(?:analisis|analisa|investigasi|telusuri|telusur)\s+(.+)$")

# Urutan penting: target pertama yang cocok menang kalau satu kalimat memuat
# beberapa kata kunci (mis. "lihat dashboard tren" -> Dashboard).
_PAGE_TARGETS = [
    ("pages/2_Dashboard.py", "Analytics Dashboard",
     ("dashboard", "dasbor", "analitik", "analytics", "statistik")),
    ("pages/1_Scraping.py", "News Scraper",
     ("scraper", "scraping", "skraping", "kumpulkan berita", "ambil berita", "cari berita", "tarik berita")),
    ("pages/3_Fenomena.py", "AI Investigator",
     ("investigator", "investigasi", "fenomena", "akar masalah", "akar permasalahan", "penyebab")),
    ("pages/4_Predictive_Intelligence.py", "Predictive Intelligence",
     ("prediksi", "prediktif", "predictive", "ramalan", "proyeksi", "forecast", "tren")),
    ("pages/5_Social_Media_Scraper.py", "Social Media Scraper",
     ("sosial media", "media sosial", "social media", "sosial", "twitter", "youtube", "facebook", "instagram", "threads")),
    ("streamlit_app.py", "Home",
     ("beranda", "halaman utama", "halaman awal", "menu utama", "home")),
]


def parse_voice_command(text: str) -> dict:
    """Teks suara -> salah satu dari:
      {"type": "none"}
      {"type": "analyze", "topic", "page", "label"}
      {"type": "navigate", "page", "label"}
      {"type": "question", "text"}
    """
    t = _PUNCT_RE.sub(" ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return {"type": "none"}

    analyze = _ANALYZE_RE.match(t)
    if analyze and analyze.group(1).strip():
        topic = analyze.group(1).strip()
        return {"type": "analyze", "topic": topic,
                "page": "pages/3_Fenomena.py", "label": "AI Investigator"}

    for page, label, keys in _PAGE_TARGETS:
        if any(k in t for k in keys):
            return {"type": "navigate", "page": page, "label": label}

    return {"type": "question", "text": t}


if __name__ == "__main__":
    n = parse_voice_command("Buka Dashboard")["type"]
    assert n == "navigate", n
    assert parse_voice_command("Buka Dashboard")["page"] == "pages/2_Dashboard.py"
    assert parse_voice_command("pergi ke halaman scraper")["page"] == "pages/1_Scraping.py"
    assert parse_voice_command("Fenomena")["page"] == "pages/3_Fenomena.py"
    assert parse_voice_command("tampilkan prediksi")["page"] == "pages/4_Predictive_Intelligence.py"
    assert parse_voice_command("media sosial")["page"] == "pages/5_Social_Media_Scraper.py"
    assert parse_voice_command("balik ke beranda")["page"] == "streamlit_app.py"
    assert parse_voice_command("investigasi banjir Jakarta") == {
        "type": "analyze", "topic": "banjir jakarta",
        "page": "pages/3_Fenomena.py", "label": "AI Investigator",
    }
    assert parse_voice_command("investigator")["type"] == "navigate"
    assert parse_voice_command("apa dampak el nino?") == {
        "type": "question", "text": "apa dampak el nino",
    }
    assert parse_voice_command("")["type"] == "none"
    assert parse_voice_command(None)["type"] == "none"
    print("voice_commands self-check ok")
