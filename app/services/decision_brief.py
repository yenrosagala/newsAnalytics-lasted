"""
Decision Intelligence — Executive Brief
=========================================
Struktur & parsing bersama untuk "Executive Brief" bergaya Decision
Intelligence: Situation, Risks, Impact, Recommendations (S-R-I-R).

Dipakai oleh:
- pages/3_Fenomena.py / AI Investigator (Executive Intelligence Brief hasil investigasi)
- app/services/pdf_service.py (render ke PDF)
- app/components/decision_brief_view.py (render ke Streamlit UI)

Kenapa dipusatkan di sini: AI Investigator dan (dulu) halaman Scraping
masing-masing punya parser JSON ad-hoc sendiri. Sekarang brief S-R-I-R
memakai skema OUTPUT yang SAMA (lihat `parse_decision_brief_json`) supaya
format & styling konsisten. Halaman Scraping tidak lagi memakai brief S-R-I-R
-- kini ia memakai Ringkasan Berita naratif (app/services/news_summary_service.py).
"""
import json
import re
from typing import Dict, List, Optional

from app.core.theme import SEVERITY_COLORS

try:
    from app.core.logger import get_logger
    logger = get_logger("DecisionBrief")
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("DecisionBrief")

VALID_SEVERITY_TIERS = ("Tinggi", "Sedang", "Rendah")

EMPTY_BRIEF: Dict = {
    "title": "",
    "situation": "",
    "risks": [],
    "impact": "",
    "recommendations": [],
    "bibliography": "",
}


def _normalize_severity(value) -> str:
    if not value:
        return "Sedang"
    value = str(value).strip().title()
    return value if value in VALID_SEVERITY_TIERS else "Sedang"


def _normalize_risks(raw_risks: List) -> List[Dict]:
    """Menyeragamkan `risks` jadi list of dict {risk, severity, rationale}.
    Menangani juga input list-of-string (fallback kalau AI abaikan skema)."""
    normalized = []
    for item in raw_risks or []:
        if isinstance(item, dict):
            risk_text = str(item.get("risk") or item.get("text") or "").strip()
            if not risk_text:
                continue
            normalized.append({
                "risk": risk_text,
                "severity": _normalize_severity(item.get("severity")),
                "rationale": str(item.get("rationale") or "").strip(),
            })
        elif isinstance(item, str) and item.strip():
            normalized.append({"risk": item.strip(), "severity": "Sedang", "rationale": ""})
    return normalized


def _normalize_recommendations(raw_recs: List) -> List[str]:
    normalized = []
    for item in raw_recs or []:
        if isinstance(item, dict):
            text = str(item.get("recommendation") or item.get("text") or "").strip()
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def parse_decision_brief_json(raw_text: str, fallback_title: str = "") -> Dict:
    """Parsing defensif untuk output JSON Decision Intelligence Brief dari AI.

    Skema yang diharapkan:
    {
      "title": "...",
      "situation": "... (esai naratif, boleh multi-paragraf, dengan sitasi [n])",
      "risks": [{"risk": "...", "severity": "Tinggi|Sedang|Rendah", "rationale": "..."}],
      "impact": "... (esai naratif implikasi/dampak, dengan sitasi [n])",
      "recommendations": ["...", "..."],
      "bibliography": "[1] ...\\n[2] ..."   (opsional -- hanya dipakai kalau AI
                                              yang menyusun daftar pustaka sendiri;
                                              di AI Investigator ini dikosongkan
                                              karena bibliografi disusun sistem)
    }

    Fallback: kalau parsing JSON gagal atau field kosong, seluruh teks mentah
    dipakai sebagai isi 'situation' supaya tidak ada informasi yang hilang,
    hanya saja tidak terstruktur.
    """
    if not raw_text:
        brief = dict(EMPTY_BRIEF)
        brief["title"] = fallback_title
        return brief

    text = raw_text.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        data = json.loads(text)
        return _brief_from_data(data, fallback_title)
    except Exception as first_err:
        # Model kadang membungkus JSON yang sebenarnya valid dengan basa-basi
        # sebelum/sesudahnya ("Tentu, ini brief-nya:\n{...}\nSemoga membantu!"),
        # terutama model lokal yang lebih kecil. Coba ekstrak substring
        # {...} terluar sebelum benar-benar menyerah ke fallback teks polos.
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                logger.info("Berhasil parsing JSON setelah ekstraksi substring {...}.")
                return _brief_from_data(data, fallback_title)
            except Exception:
                pass

        logger.warning(f"Gagal parsing JSON decision brief, fallback ke teks polos: {first_err}")
        brief = dict(EMPTY_BRIEF)
        brief["title"] = fallback_title
        brief["situation"] = text
        return brief


def _brief_from_data(data: Dict, fallback_title: str) -> Dict:
    title = str(data.get("title") or "").strip() or fallback_title
    return {
        "title": title,
        "situation": str(data.get("situation") or "").strip(),
        "risks": _normalize_risks(data.get("risks") or []),
        "impact": str(data.get("impact") or "").strip(),
        "recommendations": _normalize_recommendations(data.get("recommendations") or []),
        "bibliography": str(data.get("bibliography") or "").strip(),
    }


def serialize_brief(brief: Dict) -> str:
    """Serialisasi brief jadi JSON string untuk disimpan di kolom teks DB
    (mis. tabel `executive_summaries` / `root_cause_analysis`)."""
    return json.dumps(brief, ensure_ascii=False)


def deserialize_brief(raw: Optional[str], fallback_title: str = "") -> Dict:
    """Kebalikan dari serialize_brief, dengan fallback untuk data LAMA di DB
    yang masih berupa esai teks polos (sebelum fitur Decision Intelligence
    Brief ini ada) -- supaya cache lama tidak error, hanya tampil sebagai
    'situation' tanpa struktur risks/impact/recommendations."""
    if not raw:
        brief = dict(EMPTY_BRIEF)
        brief["title"] = fallback_title
        return brief

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "situation" in data:
            brief = dict(EMPTY_BRIEF)
            brief.update(data)
            if not brief.get("title"):
                brief["title"] = fallback_title
            return brief
    except Exception:
        pass

    # Data lama (pra-Decision Intelligence): teks esai polos.
    brief = dict(EMPTY_BRIEF)
    brief["title"] = fallback_title
    brief["situation"] = raw
    return brief


def is_brief_empty(brief: Dict) -> bool:
    return not any([
        brief.get("situation"),
        brief.get("risks"),
        brief.get("impact"),
        brief.get("recommendations"),
    ])