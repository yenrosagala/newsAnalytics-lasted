"""Palet warna & layout grafik Plotly bersama untuk seluruh app.

Nama konstanta mengikuti MAKNA, bukan nilainya -- jangan digabung hanya karena
hex-nya sama. Contoh: "Tinggi" itu hijau di TIER_COLORS (keyakinan tinggi =
bagus) tapi merah di SEVERITY_COLORS (severity tinggi = urgent).
"""

# --- Warna dasar (JARVIS HUD: glow cyan di atas navy-black) ---
ACCENT = "#22d3ee"                 # cyan utama: aksen, garis, progres
ACCENT_2 = "#38bdf8"               # cyan muda: gradien / sekunder
MUTED = "#7fa8c9"                  # teks sekunder / kategori netral
TEXT = "#dff3ff"                   # teks judul & label grafik
AMBER = "#fbbf24"                  # peringatan / level menengah
POSITIVE = "#34d399"               # hijau
NEGATIVE = "#f87171"               # merah
GRADIENT = ["#0e3a52", ACCENT]     # skala berurutan (bar/heatmap)

# --- Sentimen (kunci ganda: Title Case & UPPER, sumber memakai dua-duanya) ---
SENTIMENT_COLORS = {
    "Positive": POSITIVE, "Negative": NEGATIVE, "Neutral": MUTED,
    "POSITIVE": POSITIVE, "NEGATIVE": NEGATIVE, "NEUTRAL": MUTED,
}

# --- Severity (Tinggi = paling urgent = merah) ---
SEVERITY_COLORS = {"Tinggi": NEGATIVE, "Sedang": AMBER, "Rendah": POSITIVE}

# --- Tingkat keyakinan (Tinggi = paling yakin = hijau; KEBALIKAN severity) ---
TIER_COLORS = {"Tinggi": POSITIVE, "Sedang": AMBER, "Rendah": NEGATIVE}

# --- Layout Plotly bersama; margin/axis boleh ditimpa per grafik ---
CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color=TEXT,
    title_font_color=TEXT,
    margin=dict(t=48, b=10, l=10, r=10),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        bgcolor="rgba(8,18,32,0.65)", bordercolor="rgba(56,189,248,0.30)", borderwidth=1,
    ),
)


def sentiment_color(value, neutral: str = MUTED) -> str:
    """Warna untuk nilai sentimen apa pun casing/bahasanya (Positive/positif)."""
    v = str(value).strip().lower() if value is not None else ""
    if v.startswith("pos"):
        return POSITIVE
    if v.startswith("neg"):
        return NEGATIVE
    return neutral
