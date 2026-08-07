import requests
from typing import Tuple

from app.core.config import _get_secret

GWEN_AI_BASE_URL = "https://simatoa.web.id/site/qwen"
GWEN_REQUEST_TIMEOUT_SECONDS = 60
# Ambang aman kasar untuk panjang query string sebelum kita berpindah ke POST.
# Prompt recursive-analysis / narasi eksekutif bisa berisi banyak artikel dan
# gampang melewati batas URL yang lazim (umumnya ~8KB) kalau dikirim via GET.
GWEN_GET_SAFE_PROMPT_CHARS = 3000


def call_gwen_ai(prompt: str) -> Tuple[bool, str]:
    """
    Calls the Gwen AI endpoint with the given prompt.
    Fetches credentials from Streamlit secrets at the time of function call.
    Returns a tuple: (success: bool, result: str).
    The result is the AI's response (text) on success, or an error message on failure.
    """
    gwen_username_value = _get_secret("GWEN_USERNAME")
    gwen_password_value = _get_secret("GWEN_PASSWORD")

    if not gwen_username_value or not gwen_password_value:
        return False, "Gwen AI credentials (GWEN_USERNAME, GWEN_PASSWORD) are not set in Streamlit secrets."

    payload = {
        "username": gwen_username_value,
        "password": gwen_password_value,
        "prompt": prompt,
    }

    # Prompt panjang (mis. korpus recursive 5-Why / ringkasan eksekutif) -> POST,
    # supaya tidak kena limit panjang URL / query string di server/proxy.
    # Prompt pendek -> tetap GET seperti semula untuk kompatibilitas endpoint lama.
    use_post = len(prompt) > GWEN_GET_SAFE_PROMPT_CHARS

    try:
        if use_post:
            response = requests.post(GWEN_AI_BASE_URL, data=payload, timeout=GWEN_REQUEST_TIMEOUT_SECONDS)
        else:
            response = requests.get(GWEN_AI_BASE_URL, params=payload, timeout=GWEN_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return True, response.text  # Assuming the response is plain text from the API
    except requests.exceptions.RequestException as e:
        if use_post:
            # Endpoint mungkin belum mendukung POST -- coba GET sebagai upaya terakhir
            # (masih berisiko 414 kalau prompt memang sangat panjang, tapi lebih baik
            # daripada langsung menyerah).
            try:
                response = requests.get(GWEN_AI_BASE_URL, params=payload, timeout=GWEN_REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                return True, response.text
            except requests.exceptions.RequestException as e2:
                return False, f"Failed to get response from Gwen AI (POST failed: {e}; GET fallback also failed: {e2})"
        return False, f"Failed to get response from Gwen AI: {e}"