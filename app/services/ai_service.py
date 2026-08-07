# app/services/ai_service.py
import os
from typing import List
import requests

from app.core.logger import get_logger

try:
    import streamlit as st
except Exception:
    st = None

logger = get_logger("AIService")

# Endpoint chat-completions OpenRouter (kompatibel-format OpenAI). Model
# aktual dipilih lewat field "model" di body request (lihat self.model_name),
# bukan lewat URL -- OpenRouter merutekan ke provider yang benar-benar
# menjalankan model itu di baliknya.
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Endpoint ringan untuk memvalidasi key + lihat sisa kredit/limit, TANPA
# memakan kuota chat-completion -- dipakai oleh check_status().
OPENROUTER_KEY_INFO_URL = "https://openrouter.ai/api/v1/key"

OLLAMA_CONNECTION_ERROR_HINT = (
    "Tidak bisa terhubung ke Ollama di {base_url}. Pastikan Ollama berjalan "
    "dan model sudah ter-pull."
)
# Timeout pendek KHUSUS untuk warm_up() -- ini cuma "apakah Ollama ada &
# responsif", bukan generate() sungguhan, jadi tidak boleh ikut menunggu
# selama self.ollama_timeout (default 120s). warm_up() dipanggil sinkron di
# jalur render halaman Home -- timeout yang kelamaan di sini = halaman
# kelihatan blank/hang, bukan cuma AI-nya yang lambat.
WARM_UP_TIMEOUT_SECONDS = 5


class EmptyResponseError(Exception):
    """AI merespons tetapi teks kosong."""
    pass


def _build_messages(prompt: str, system_prompt: str = None, force_json: bool = False) -> List[dict]:
    """Susun daftar `messages` OpenAI-compatible dengan pemisahan role yang
    KONSISTEN dipakai baik oleh _call_openrouter maupun _call_ollama
    (sebelumnya OpenRouter selalu mengirim semuanya sebagai satu blok
    "user" tanpa system message sama sekali, sementara Ollama dapat system
    message tambahan hanya untuk force_json -- dua jalur AI di app ini jadi
    berperilaku beda tergantung provider mana yang kebetulan aktif).

    - `system_prompt`: instruksi TETAP dari pemanggil (peran analis,
      kerangka tugas, skema output JSON) -- konstan antar-panggilan untuk
      task yang sama, TIDAK mengandung data dari luar/tidak tepercaya.
    - `force_json`: kalau True, tambahkan instruksi format JSON singkat ke
      system message yang sama (bukan pesan system terpisah).
    - `prompt`: korpus/data DINAMIS (artikel hasil scraping, ringkasan
      level, riwayat chat, pertanyaan pengguna) -- selalu jadi pesan
      "user", termasuk kalau isinya berasal dari sumber luar yang berpotensi
      berisi instruksi tersisip (prompt injection) -- role "user" (bukan
      "system") memberi model sinyal bahwa ini data yang SEDANG DIANALISIS,
      bukan instruksi yang harus dipatuhi.

    Kalau `system_prompt` tidak diberikan (pemanggil lama yang belum
    dimigrasi), perilaku persis seperti sebelumnya: satu pesan "user" saja
    (ditambah system JSON-only kalau force_json, sama seperti perilaku lama
    Ollama) -- supaya migrasi bertahap tidak memecah pemanggil yang belum
    diupdate.
    """
    system_parts = []
    if system_prompt:
        system_parts.append(system_prompt.strip())
    if force_json:
        system_parts.append("Balas HANYA dengan JSON valid, tanpa teks lain, tanpa markdown code fence.")

    messages = []
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})
    messages.append({"role": "user", "content": prompt})
    return messages


class AIService:
    """Wrapper AI menggunakan OpenRouter (model GLM-5.2 dari Z.ai secara
    default) sebagai otak utama.

    Sebelumnya otak utama adalah Gemini dengan fallback ke Ollama lokal.
    Diganti ke OpenRouter karena dua masalah reliabilitas yang dialami
    langsung: (1) Gemini sering kena limit/quota, (2) Ollama lokal dibatasi
    kemampuan hardware (lambat/kadang gagal load model). OpenRouter dipakai
    karena satu API key bisa merutekan ke banyak provider/model dengan
    kapasitas jauh lebih besar daripada tier gratis Gemini, dan tidak
    tergantung hardware lokal sama sekali.

    Ollama TETAP dipertahankan sebagai fallback darurat paling akhir (mis.
    OpenRouter kehabisan kredit atau down total) -- bukan lagi otak utama,
    hanya jaring pengaman. Kalau ternyata itu juga tidak diinginkan (mengingat
    keluhan soal keterbatasan hardware-nya), gampang dicabut: hapus panggilan
    _call_ollama() di generate() dan biarkan generate() langsung raise begitu
    OpenRouter gagal.
    """

    def __init__(self):
        self.api_keys: List[str] = self._load_api_keys()
        self.active_index = 0
        self.model_name = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.5-air:free").strip()
        # --- Rotasi/fallback model OpenRouter ---
        # OpenRouter mendukung fallback OTOMATIS antar beberapa model lewat
        # field "models" (array, urutan prioritas) di body request -- kalau
        # model pertama error/down/kena rate-limit/moderasi, OpenRouter
        # otomatis coba model berikutnya di daftar, TANPA perlu retry manual
        # di sisi aplikasi. Ini beda dari `provider.order` (yang memilih
        # provider INFRA untuk satu model yang sama) -- di sini yang
        # dirotasi adalah model-nya sendiri.
        # Override lewat env var OPENROUTER_MODEL_ORDER (dipisah koma) kalau
        # perlu daftar lain; default-nya daftar model gratis di bawah ini.
        # CATATAN PENTING: katalog model ":free" di OpenRouter berputar
        # SANGAT cepat -- model gratis bisa didelist/diganti provider dalam
        # hitungan hari/minggu tanpa pemberitahuan. Hardcode daftar slug
        # spesifik gampang basi (model jadi 404/error). Karena itu daftar di
        # bawah SENGAJA diakhiri dengan "openrouter/free" -- itu bukan model
        # sungguhan, tapi Free Models Router bawaan OpenRouter yang otomatis
        # memilih SATU model gratis apa pun yang sedang tersedia saat itu.
        # Jadi walau semua slug ":free" spesifik di atasnya basi/di-delist,
        # "openrouter/free" tetap jadi jaring pengaman gratis yang hidup.
        default_model_order = (
            "z-ai/glm-4.5-air:free,"
            "openai/gpt-oss-20b:free,"
            "openrouter/free"
        )
        raw_model_order = os.getenv("OPENROUTER_MODEL_ORDER", default_model_order)
        self.model_order: List[str] = [m.strip() for m in raw_model_order.split(",") if m.strip()]
        self.allow_fallbacks = os.getenv("OPENROUTER_ALLOW_FALLBACKS", "true").strip().lower() != "false"
        self.openrouter_timeout = int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", 120))
        # Header opsional yang direkomendasikan OpenRouter untuk atribusi app
        # di leaderboard mereka (openrouter.ai/rankings) -- request tetap
        # jalan normal tanpa header ini, murni informasional.
        self.openrouter_site_url = os.getenv("OPENROUTER_SITE_URL", "").strip() or None
        self.openrouter_app_name = os.getenv("OPENROUTER_APP_NAME", "NewsAnalytics AI Hub").strip() or None

        # --- Ollama sebagai fallback darurat (BUKAN otak utama lagi) ---
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.ollama_fallback_model = os.getenv("OLLAMA_MODEL_FAST", "llama3:8b-instruct-q8_0").strip()
        self.ollama_timeout = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", 120))
        self.ollama_num_ctx = int(os.getenv("OLLAMA_NUM_CTX", 8192))
        # 4096 output token berlebihan untuk ekstraksi terstruktur; 1536 cukup
        # lapang dan lebih cepat. Naikkan lewat env var kalau perlu output
        # lebih panjang.
        self.ollama_num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", 1536))
        # Keep-alive lama supaya model tetap "hangat" di RAM/VRAM antar-request.
        self.ollama_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

        if not self.api_keys:
            logger.warning(
                "OPENROUTER_API_KEYS kosong/tidak ditemukan di secrets.toml -- "
                "semua request akan langsung memakai fallback lokal Ollama."
            )
        else:
            logger.info(
                f"AI Service (OpenRouter) terkonfigurasi dengan {len(self.api_keys)} "
                f"API key, model rotation order={self.model_order or [self.model_name]}, "
                f"allow_fallbacks={self.allow_fallbacks}."
            )

    def _load_api_keys(self) -> List[str]:
        raw = None
        if st is not None:
            try:
                raw = st.secrets.get("OPENROUTER_API_KEYS", None)
            except Exception:
                raw = None

        if raw is None:
            raw = os.getenv("OPENROUTER_API_KEYS", "")

        if isinstance(raw, str):
            keys = [k.strip() for k in raw.split(",") if k.strip()]
        elif isinstance(raw, (list, tuple)):
            keys = [str(k).strip() for k in raw if str(k).strip()]
        else:
            keys = []
        return keys

    def _rotate_key(self) -> None:
        """OpenRouter tidak butuh objek client stateful seperti Gemini --
        cukup pindah index, key yang dipakai di request berikutnya otomatis
        berubah (lihat _call_openrouter)."""
        if not self.api_keys:
            return
        self.active_index = (self.active_index + 1) % len(self.api_keys)

    def _openrouter_headers(self, api_key: str) -> dict:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            headers["X-Title"] = self.openrouter_app_name
        return headers

    def _call_openrouter(self, prompt: str, force_json: bool = False, reasoning: bool = False, system_prompt: str = None) -> str:
        if not self.api_keys:
            raise Exception("OpenRouter API key belum terkonfigurasi.")
        api_key = self.api_keys[self.active_index]

        payload = {
            # "models": array prioritas untuk rotasi/fallback OTOMATIS antar
            # model kalau model pertama gagal (down/rate-limit/moderasi) --
            # lihat OPENROUTER_MODEL_ORDER di __init__. "model" (singular)
            # tetap dikirim sebagai fallback terakhir kalau self.model_order
            # kosong (mis. di-set eksplisit ke "" lewat env var), supaya
            # perilaku lama (satu model tetap) tidak rusak.
            "models" if self.model_order else "model": self.model_order or self.model_name,
            "provider": {"allow_fallbacks": self.allow_fallbacks},
            # Pemisahan role system/user: instruksi TETAP (peran analis,
            # kerangka tugas, skema output) dikirim sebagai "system" kalau
            # pemanggil menyediakannya lewat `system_prompt` -- korpus/data
            # DINAMIS (artikel, ringkasan level, pertanyaan pengguna, dll,
            # yang bisa berisi teks dari sumber luar/tidak tepercaya) selalu
            # tetap di "user". Ini memberi model sinyal hierarki yang lebih
            # jelas (instruksi vs data-yang-dianalisis) dibanding menumpuk
            # semuanya ke satu blok "user" -- lihat _build_system_message().
            "messages": _build_messages(prompt, system_prompt, force_json),
            # GLM-5.2 adalah reasoning model -- dokumentasi resminya default ke
            # thinking ENABLED + reasoning_effort "max" di setiap contoh. Untuk
            # tugas ekstraksi terstruktur (rangkuman, causes, next_keywords,
            # decision brief) yang dipakai app ini, thinking mode HANYA
            # menambah latensi tanpa menambah kualitas -- 1 investigasi AI
            # Investigator = sampai 6 panggilan berurutan, jadi kalau tiap
            # panggilan diam-diam "berpikir" beberapa puluh detik, totalnya
            # berasa "tidak selesai-selesai". Default-kan MATI, dan biarkan
            # pemanggil yang benar-benar butuh reasoning mendalam nyalakan
            # lewat parameter `reasoning=True`.
            "thinking": {"type": "enabled" if reasoning else "disabled"},
        }
        if reasoning:
            payload["reasoning_effort"] = "max"
        if force_json:
            # Format response_format OpenAI-compatible -- GLM-5.2 mendukung
            # Structured Output sesuai dokumentasi Z.ai.
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=self._openrouter_headers(api_key),
                json=payload,
                timeout=self.openrouter_timeout,
            )
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"Tidak bisa terhubung ke OpenRouter: {e}")
        except requests.exceptions.Timeout as e:
            raise Exception(f"OpenRouter timeout setelah {self.openrouter_timeout}s: {e}")

        if response.status_code == 401:
            raise Exception("OpenRouter API key ditolak (401 Unauthorized) -- key salah/kadaluarsa.")
        if response.status_code == 429:
            raise Exception("OpenRouter rate limit tercapai / kredit habis (429).")
        if response.status_code in (400, 404):
            # Biasanya artinya salah satu slug ":free" di model_order sudah
            # basi/di-delist provider (katalog free berubah cepat -- lihat
            # catatan di __init__). "openrouter/free" di akhir daftar tetap
            # jadi jaring pengaman selama ini bukan satu-satunya model di
            # array.
            raise Exception(
                f"OpenRouter menolak permintaan (HTTP {response.status_code}) -- kemungkinan salah satu "
                f"model di model_order sudah tidak tersedia/di-delist. Detail: {response.text[:300]}"
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"OpenRouter mengembalikan error HTTP {response.status_code}: {e}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            # OpenRouter kadang mengembalikan error di body walau status HTTP 200.
            err = data.get("error", {})
            raise Exception(f"OpenRouter tidak mengembalikan choices: {err.get('message', data)}")

        text = (choices[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise EmptyResponseError("OpenRouter mengembalikan respons kosong.")

        actual_model = data.get("model")
        if actual_model:
            logger.info(f"OpenRouter menjawab pakai model: {actual_model}")
        return text

    def _call_ollama(self, prompt: str, force_json: bool = False, timeout_override: int = None, system_prompt: str = None) -> str:
        """Panggil Ollama lewat /api/chat (bukan /api/generate).

        /api/chat + format=json jauh lebih taat skema daripada mengirim
        prompt mentah ke /api/generate, mengurangi kasus respons kosong yang
        butuh retry.

        `timeout_override`: pakai timeout ini alih-alih self.ollama_timeout
        -- dipakai warm_up() supaya ping cepat tidak ikut menunggu selama
        timeout generate() yang sungguhan (bisa 120s).
        """
        timeout = timeout_override if timeout_override is not None else self.ollama_timeout
        model_name = self.ollama_fallback_model
        messages = _build_messages(prompt, system_prompt, force_json)

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": self.ollama_num_ctx,
                "num_predict": self.ollama_num_predict,
            },
            "keep_alive": self.ollama_keep_alive,
        }
        if force_json:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/chat", json=payload, timeout=timeout
            )
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"{OLLAMA_CONNECTION_ERROR_HINT.format(base_url=self.ollama_base_url)} Detail: {e}")

        if response.status_code == 404:
            raise Exception(
                f"Model Ollama '{model_name}' tidak ditemukan. "
                f"Jalankan perintah terminal: ollama pull {model_name}"
            )
        response.raise_for_status()
        data = response.json()
        text = (data.get("message", {}).get("content") or "").strip()

        if not text and force_json:
            payload.pop("format", None)
            response = requests.post(
                f"{self.ollama_base_url}/api/chat", json=payload, timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            text = (data.get("message", {}).get("content") or "").strip()

        if not text:
            raise Exception(f"Ollama (model '{model_name}') mengembalikan respons kosong.")
        return text

    def warm_up(self) -> bool:
        """Muat model ke memori Ollama lebih awal (saat app start) supaya
        KALAU sampai jatuh ke fallback, request pertama tidak menanggung
        biaya cold-load model. OpenRouter (otak utama) tidak butuh warm-up
        sama sekali -- tidak ada model lokal yang perlu dimuat.

        DIPANGGIL SECARA SINKRON saat halaman Home pertama kali dimuat,
        SEBELUM konten apa pun dirender -- jadi kalau ini lambat, seluruh
        halaman kelihatan blank/nge-hang, bukan cuma AI-nya. Dua pengaman:
        (1) di-skip total kalau OpenRouter sudah terkonfigurasi -- warm-up
        Ollama cuma relevan kalau Ollama benar-benar akan dipakai (fallback
        darurat), tidak ada gunanya menunggu-nunggu Ollama di jalur kritis
        page-load kalau OpenRouter yang bakal dipakai; (2) timeout PENDEK
        khusus untuk ping ini (beda dari self.ollama_timeout yang dipakai
        generate() sungguhan, defaultnya 120s -- terlalu lama untuk sekadar
        'apakah Ollama ada?')."""
        if self.api_keys:
            logger.info("OpenRouter terkonfigurasi -- warm-up Ollama dilewati (fallback tidak akan dipakai kecuali OpenRouter gagal).")
            return False
        try:
            self._call_ollama("ping", force_json=False, timeout_override=WARM_UP_TIMEOUT_SECONDS)
            logger.info(f"Ollama fallback '{self.ollama_fallback_model}' sudah dimuat & siap (warm).")
            return True
        except Exception as e:
            logger.info(f"Warm-up Ollama fallback gagal/tidak tersedia (tidak masalah selama OpenRouter jalan): {e}")
            return False

    def check_status(self) -> dict:
        """Cek status AI provider secara RINGAN (tanpa generate() penuh) --
        dipakai oleh status bar di setiap halaman, jadi harus cepat & murah.
        OpenRouter: panggil endpoint /api/v1/key (bukan chat completion) untuk
        memvalidasi key + baca sisa kredit, dengan timeout pendek.
        Ollama: 1 request kecil ke /api/tags dengan timeout pendek (hanya
        relevan kalau OpenRouter tidak terkonfigurasi sama sekali).
        Return: {"provider": str, "ok": bool, "detail": str}
        """
        if self.api_keys:
            api_key = self.api_keys[self.active_index]
            try:
                resp = requests.get(
                    OPENROUTER_KEY_INFO_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=5,
                )
                if resp.status_code == 401:
                    return {
                        "provider": "OpenRouter",
                        "ok": False,
                        "detail": f"{len(self.api_keys)} API key ada tapi key aktif ditolak (401 Unauthorized).",
                    }
                resp.raise_for_status()
                info = (resp.json() or {}).get("data", {}) or {}
                usage = info.get("usage")
                limit = info.get("limit")
                detail = f"{len(self.api_keys)} API key terkonfigurasi, model order={self.model_order or [self.model_name]}"
                if usage is not None:
                    detail += f", terpakai ${usage:.2f}"
                    if limit is not None:
                        detail += f" dari limit ${limit:.2f}"
                return {"provider": "OpenRouter", "ok": True, "detail": detail}
            except requests.exceptions.RequestException as e:
                return {
                    "provider": "OpenRouter",
                    "ok": False,
                    "detail": f"Key terkonfigurasi tapi validasi gagal (invalid/timeout/kredit habis?): {e}",
                }

        try:
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=2)
            resp.raise_for_status()
            return {"provider": "Ollama (fallback lokal)", "ok": True, "detail": self.ollama_fallback_model}
        except Exception as e:
            return {
                "provider": "Tidak ada",
                "ok": False,
                "detail": f"OpenRouter tidak dikonfigurasi & Ollama tidak terjangkau di {self.ollama_base_url} ({e})",
            }

    def generate(self, prompt: str, force_json: bool = False, reasoning: bool = False, system_prompt: str = None) -> str:
        """OpenRouter (GLM-5.2) dulu sebagai otak utama, fallback ke Ollama
        lokal HANYA kalau OpenRouter gagal total/tidak terkonfigurasi.

        `reasoning=False` (default) mematikan thinking mode GLM-5.2 -- cocok
        untuk tugas ekstraksi terstruktur yang dipakai app ini (rangkuman,
        causes, decision brief). Set `reasoning=True` di titik panggil kalau
        suatu saat butuh penalaran berlapis yang sungguhan (jarang perlu di
        app ini).

        `system_prompt`: instruksi TETAP (opsional) yang dikirim sebagai
        pesan role "system", terpisah dari `prompt` (data/korpus dinamis
        yang tetap role "user") -- diteruskan APA ADANYA ke kedua provider
        (OpenRouter & Ollama) lewat _build_messages() supaya perilakunya
        konsisten terlepas dari provider mana yang aktif. Pemanggil lama
        yang belum dimigrasi cukup tidak mengisi parameter ini."""
        if self.api_keys:
            last_error = None
            attempts = 0
            while attempts < len(self.api_keys):
                try:
                    return self._call_openrouter(prompt, force_json=force_json, reasoning=reasoning, system_prompt=system_prompt)
                except Exception as e:
                    last_error = e
                    logger.warning(f"OpenRouter gagal ({e}), merotasi key...")
                    self._rotate_key()
                    attempts += 1
            logger.warning(f"OpenRouter gagal total ({last_error}). Mencoba fallback ke Ollama lokal...")
        else:
            logger.info("OpenRouter tidak terkonfigurasi (OPENROUTER_API_KEYS kosong). Memakai Ollama lokal.")

        try:
            return self._call_ollama(prompt, force_json=force_json, system_prompt=system_prompt)
        except Exception as ollama_err:
            raise Exception(
                f"OpenRouter gagal/tidak terkonfigurasi dan fallback Ollama lokal juga gagal: {ollama_err}"
            )

    def analyze_article(self, full_text: str) -> dict:
        """Satu kali request untuk mendapatkan Rangkuman & Sentimen sekaligus."""
        if not full_text or len(full_text.strip()) < 150:
            return {"summary": "Konten berita terlalu pendek untuk dirangkum.", "sentiment": "Neutral"}

        prompt = f"""Bertindaklah sebagai analis media profesional. Analisis berita berikut:

{full_text}

Berikan hasil persis dalam format berikut (tanpa basa-basi):
SENTIMEN: [Isi dengan Positif, Negatif, atau Netral]
RANGKUMAN:
- [Poin 1]
- [Poin 2]
- [Poin 3]"""

        try:
            text_res = self.generate(prompt)
            sentiment_label = "Neutral"
            if "SENTIMEN: Positif" in text_res or "SENTIMEN: POSITIF" in text_res:
                sentiment_label = "Positive"
            elif "SENTIMEN: Negatif" in text_res or "SENTIMEN: NEGATIF" in text_res:
                sentiment_label = "Negative"
            return {"summary": text_res, "sentiment": sentiment_label}
        except Exception as e:
            logger.error(f"Gagal memproses AI: {str(e)}")
            return {"summary": f"Gagal memproses rangkuman AI: {str(e)}", "sentiment": "Neutral"}


# Singleton instance
ai_service = AIService()