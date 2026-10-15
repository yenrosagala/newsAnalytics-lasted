"""Jembatan suara Jarvis: komponen mikrofon + bar perintah global.

Dua lapis:
  1. render_voice_input() -- pembungkus tipis di atas komponen custom
     (jarvis_voice/index.html) yang memakai Web Speech API bawaan browser untuk
     mengenali suara. Tidak ada dependensi server, tidak ada API key, dan audio
     tidak dikirim ke backend -- pengenalan terjadi di browser pengguna.
  2. render_jarvis_voice_bar() -- bar perintah di sidebar (tampil di semua
     halaman) yang menerjemahkan hasil pengenalan lewat
     app.services.voice_commands.parse_voice_command menjadi navigasi antar
     modul atau investigasi bertopik.

Komponen dipanggil dengan `default=None`; Streamlit mengembalikan nilai
TERAKHIR yang di-set komponen, jadi tiap dict hasil dilengkapi `id` unik dan
kita dedupe lewat session_state supaya perintah tidak diulang tiap rerun.
"""
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import declare_component

from app.services.voice_commands import parse_voice_command

_FRONTEND_DIR = Path(__file__).parent / "jarvis_voice"
_jarvis_voice = declare_component("jarvis_voice", path=str(_FRONTEND_DIR))

_PENDING_SPEECH_KEY = "jarvis_pending_speech"
_SEEN_KEY = "jarvis_voice_bar_seen"


def render_voice_input(key: str, label: str = "🎙️ Bicara", default=None):
    """Render tombol mikrofon. Kembalikan dict {text,id,status[,error]} atau None.

    `key` HARUS unik per lokasi pemakaian supaya tiap tombol punya state sendiri.
    """
    return _jarvis_voice(key=key, label=label, default=default)


def _speak(text: str) -> None:
    """Bacakan konfirmasi memakai TTS yang sudah ada di chatbot (diimpor saat
    dipanggil untuk menghindari import melingkar chatbot <-> voice_input)."""
    try:
        from app.components.chatbot import speak_text
        speak_text(text)
    except Exception:
        pass


def _handle_command(cmd: dict, raw_text: str) -> None:
    ctype = cmd.get("type")

    if ctype == "navigate":
        st.session_state[_PENDING_SPEECH_KEY] = f"Membuka {cmd['label']}."
        st.switch_page(cmd["page"])

    elif ctype == "analyze":
        topic = cmd.get("topic") or raw_text
        # 3_Fenomena.py memakai nilai ini sebagai default text_area investigasi.
        st.session_state["investigator_prefill"] = topic
        st.session_state[_PENDING_SPEECH_KEY] = f"Menyiapkan investigasi untuk: {topic}."
        st.switch_page(cmd["page"])

    elif ctype == "question":
        _speak(
            f"Belum mengerti perintah '{raw_text}'. Coba sebutkan nama modul, "
            "misalnya 'buka dashboard', atau 'investigasi banjir Jakarta'."
        )


def render_jarvis_voice_bar() -> None:
    """Bar perintah suara di sidebar. Dipanggil dari render_app_sidebar()
    sehingga tersedia di semua halaman."""
    # Konfirmasi navigasi dari run sebelumnya dibacakan DULU di halaman tujuan
    # (st.switch_page menghentikan run sebelum baris ini, jadi pending baru
    # dibacakan pada run berikutnya).
    pending = st.session_state.pop(_PENDING_SPEECH_KEY, None)
    if pending:
        _speak(pending)

    with st.sidebar:
        st.markdown('<div class="d-nav-label">Jarvis &middot; Perintah Suara</div>', unsafe_allow_html=True)
        result = render_voice_input(key="jarvis_voice_bar", label="🎙️ Bicara ke Jarvis")

    if not result:
        return

    result_id = result.get("id")
    if result_id is None or result_id == st.session_state.get(_SEEN_KEY):
        return
    st.session_state[_SEEN_KEY] = result_id

    if result.get("status") == "error":
        err = result.get("error") or "unknown"
        if err not in ("aborted", "no-speech"):
            _speak("Maaf, mikrofon tidak dapat diakses.")
        return

    text = (result.get("text") or "").strip()
    if text:
        _handle_command(parse_voice_command(text), text)
