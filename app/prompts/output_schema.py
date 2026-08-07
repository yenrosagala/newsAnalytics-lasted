OUTPUT_SCHEMA = """
FORMAT KELUARAN:
Jawab HANYA dalam format objek JSON yang valid tanpa teks tambahan di luar JSON. Gunakan struktur kunci berikut:

{
  "title": "Judul Executive Brief yang ringkas dan profesional",
  "situation": "Narasi situasi 3-6 paragraf...",
  "risks": [
    {
      "item": "Deskripsi risiko spesifik...",
      "severity": "Tinggi"
    }
  ],
  "impact": "Analisis dampak 2-4 paragraf...",
  "recommendations": [
    "Rekomendasi langkah taktis pertama...",
    "Rekomendasi langkah taktis kedua..."
  ]
}
"""