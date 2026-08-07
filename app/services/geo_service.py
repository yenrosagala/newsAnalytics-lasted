"""
Spatial Intelligence: deteksi lokasi yang disebut dalam judul/isi berita, lalu
agregasi jadi titik-titik "hotspot" di peta.

CARA KERJA & BATASAN (baca sebelum pakai):
- Database TIDAK punya kolom lat/long -- tidak ada geocoding presisi di sini.
  Lokasi dideteksi dengan mencocokkan nama provinsi/kota Indonesia yang
  disebut di teks judul + isi berita (word-boundary, case-insensitive).
- Ini artinya hasilnya adalah "di mana berita ini MENYEBUT lokasi", bukan
  "di mana peristiwa ini benar-benar terjadi". Berita yang menyebut beberapa
  kota akan dihitung untuk beberapa titik sekaligus. Cocok untuk melihat pola
  liputan media secara kasar, bukan untuk keputusan yang butuh presisi lokasi.
- Daftar lokasi sengaja dibatasi ke ibu kota provinsi + kota-kota besar yang
  namanya cukup unik (menghindari kata umum yang sering salah-cocok, mis.
  "Solo" atau "Batu" sengaja tidak dimasukkan).
"""
import re
from typing import Dict, List, Optional

import pandas as pd

# name -> (lat, lon). Ibu kota provinsi + kota besar dengan nama unik.
INDONESIA_LOCATIONS: Dict[str, tuple] = {
    "Banda Aceh": (5.5483, 95.3238), "Medan": (3.5952, 98.6722),
    "Padang": (-0.9471, 100.4172), "Pekanbaru": (0.5071, 101.4478),
    "Tanjungpinang": (0.9186, 104.4610), "Batam": (1.0456, 104.0305),
    "Jambi": (-1.6101, 103.6131), "Palembang": (-2.9761, 104.7754),
    "Pangkal Pinang": (-2.1316, 106.1169), "Bengkulu": (-3.7928, 102.2608),
    "Bandar Lampung": (-5.4292, 105.2610), "Jakarta": (-6.2088, 106.8456),
    "Bandung": (-6.9175, 107.6191), "Bekasi": (-6.2383, 106.9756),
    "Bogor": (-6.5971, 106.8060), "Depok": (-6.4025, 106.7942),
    "Tangerang": (-6.1783, 106.6319), "Semarang": (-6.9932, 110.4203),
    "Solo Raya": (-7.5755, 110.8243), "Yogyakarta": (-7.7956, 110.3695),
    "Surabaya": (-7.2575, 112.7521), "Malang": (-7.9666, 112.6326),
    "Kediri": (-7.8480, 112.0178), "Jember": (-8.1844, 113.6681),
    "Madiun": (-7.6298, 111.5239), "Serang": (-6.1200, 106.1500),
    "Denpasar": (-8.6705, 115.2126), "Mataram": (-8.5833, 116.1167),
    "Kupang": (-10.1772, 123.6070), "Pontianak": (-0.0263, 109.3425),
    "Palangkaraya": (-2.2090, 113.9213), "Banjarmasin": (-3.3186, 114.5944),
    "Samarinda": (-0.5022, 117.1536), "Balikpapan": (-1.2379, 116.8529),
    "Tanjung Selor": (2.8386, 117.3676), "Manado": (1.4748, 124.8421),
    "Gorontalo": (0.5435, 123.0568), "Palu": (-0.8917, 119.8707),
    "Mamuju": (-2.6785, 118.8880), "Makassar": (-5.1477, 119.4327),
    "Kendari": (-3.9450, 122.4989), "Ambon": (-3.6954, 128.1814),
    "Ternate": (0.7833, 127.3833), "Jayapura": (-2.5337, 140.7181),
    "Manokwari": (-0.8615, 134.0620), "Merauke": (-8.4667, 140.4000),
    "Nabire": (-3.3667, 135.4833), "Wamena": (-4.0833, 138.9500),
    "Sorong": (-0.8833, 131.2500),
}

_PATTERNS = {
    name: re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
    for name in INDONESIA_LOCATIONS
}


def extract_locations_from_text(text: str) -> List[str]:
    """Cari nama lokasi yang disebut dalam satu string teks. Return list unik,
    urutan kemunculan pertama."""
    if not text or not isinstance(text, str):
        return []
    found = []
    for name, pattern in _PATTERNS.items():
        if pattern.search(text):
            found.append(name)
    return found


def build_location_hotspots(
    df: pd.DataFrame,
    title_col: str = "judul",
    content_col: str = "isi_konten",
    sentiment_col: Optional[str] = "Sentimen",
) -> pd.DataFrame:
    """Bangun tabel hotspot: satu baris per lokasi terdeteksi, dengan jumlah
    sebutan dan (jika ada kolom sentimen) sentimen dominan.

    Return kolom: location, lat, lon, mention_count, dominant_sentiment
    """
    if df.empty:
        return pd.DataFrame(columns=["location", "lat", "lon", "mention_count", "dominant_sentiment"])

    rows = []
    for _, row in df.iterrows():
        text = " ".join(
            str(row.get(c, "")) for c in (title_col, content_col) if c in df.columns
        )
        locations = extract_locations_from_text(text)
        for loc in locations:
            rows.append({"location": loc, "sentiment": row.get(sentiment_col) if sentiment_col else None})

    if not rows:
        return pd.DataFrame(columns=["location", "lat", "lon", "mention_count", "dominant_sentiment"])

    hits_df = pd.DataFrame(rows)
    counts = hits_df.groupby("location").size().reset_index(name="mention_count")

    if sentiment_col and "sentiment" in hits_df.columns:
        dominant = (
            hits_df.dropna(subset=["sentiment"])
            .groupby("location")["sentiment"]
            .agg(lambda s: s.value_counts().idxmax() if not s.empty else None)
            .reset_index()
            .rename(columns={"sentiment": "dominant_sentiment"})
        )
        counts = counts.merge(dominant, on="location", how="left")
    else:
        counts["dominant_sentiment"] = None

    counts["lat"] = counts["location"].map(lambda l: INDONESIA_LOCATIONS[l][0])
    counts["lon"] = counts["location"].map(lambda l: INDONESIA_LOCATIONS[l][1])

    return counts.sort_values("mention_count", ascending=False).reset_index(drop=True)
