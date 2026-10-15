"""Cek cepat logika sentimen->warna di app/core/theme.py.

Jalankan: python test_theme.py
"""
from app.core.theme import ACCENT, MUTED, NEGATIVE, POSITIVE, SENTIMENT_COLORS, sentiment_color

assert sentiment_color("Positive") == POSITIVE
assert sentiment_color("POSITIVE") == POSITIVE
assert sentiment_color("positif") == POSITIVE
assert sentiment_color("Negative") == NEGATIVE
assert sentiment_color("negatif") == NEGATIVE
assert sentiment_color("Netral") == MUTED
assert sentiment_color(None, neutral=ACCENT) == ACCENT
assert SENTIMENT_COLORS["Neutral"] == MUTED

print("theme OK")
