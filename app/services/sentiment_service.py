import re
from app.core.logger import setup_logger

logger = setup_logger("sentiment_service")


class SentimentService:
    """Analisis sentimen artikel berbasis lexicon Bahasa Indonesia.

    Sebelumnya sempat dicoba pakai AI (LLM) per-artikel, tapi itu boros
    token/request karena dipanggil di dalam loop scraping (bisa puluhan
    artikel per run) -- jadi dikembalikan ke pendekatan lexicon murni,
    TANPA panggilan AI sama sekali, tapi diperbaiki dari versi lama:

    1. Lexicon jauh lebih besar (~150+ kata tiap sisi, mencakup konteks
       ekonomi, sosial, politik, bencana, hukum) dibanding versi lama yang
       cuma 11 kata per sisi.
    2. Penanganan NEGASI -- kata seperti "tidak", "bukan", "belum", "jangan"
       yang muncul tepat sebelum kata sentimen membalik polaritasnya
       ("tidak bagus" harus dihitung negatif, bukan positif).
    3. Kata PENGUAT (intensifier) seperti "sangat", "sangat sekali" memberi
       bobot lebih besar pada kata sentimen yang mengikutinya.
    4. Skoring berbasis hitungan kata mentah (bukan TF-IDF) -- TF-IDF pada
       satu dokumen tunggal tidak banyak berguna (semua term-frequency
       relatif terhadap dokumen itu sendiri), sedangkan hitungan kata
       lexicon langsung + normalisasi panjang teks lebih representatif
       untuk kasus ini.
    """

    NEGATION_WORDS = {"tidak", "tak", "bukan", "belum", "jangan", "tanpa", "kurang"}
    INTENSIFIER_WORDS = {"sangat", "amat", "sekali", "sungguh", "benar-benar"}

    def __init__(self):
        self.positif_lexicon = {
            # Ekonomi & bisnis
            "untung", "keuntungan", "laba", "naik", "kenaikan", "meningkat", "peningkatan",
            "tumbuh", "pertumbuhan", "berkembang", "surplus", "stabil", "kestabilan", "menguat",
            "penguatan", "pulih", "pemulihan", "investasi", "ekspansi", "efisien", "produktif",
            "untung besar", "cuan", "profit", "berkah", "sejahtera", "kesejahteraan", "makmur",
            # Umum / kualitas
            "bagus", "baik", "membaik", "positif", "sukses", "berhasil", "keberhasilan", "unggul",
            "prestasi", "berprestasi", "maju", "kemajuan", "inovasi", "inovatif", "optimis",
            "optimistis", "harapan", "berharap", "gemilang", "cemerlang", "istimewa", "hebat",
            "luar biasa", "memuaskan", "kepuasan", "apresiasi", "terpuji", "dukungan", "mendukung",
            "solutif", "solusi", "efektif", "aman", "nyaman", "damai", "kondusif", "kompak",
            "harmonis", "kerjasama", "kolaborasi", "sinergi", "terobosan", "peluang", "prospek",
            # Sosial / kesehatan
            "sembuh", "kesembuhan", "sehat", "membaik", "terselamatkan", "selamat", "penyelamatan",
            "bantuan", "membantu", "meringankan", "terpenuhi", "cukup", "memadai", "layak",
            # Politik / hukum
            "menang", "kemenangan", "disahkan", "diloloskan", "diterima", "disetujui", "persetujuan",
            "kompromi", "rekonsiliasi", "transparan", "akuntabel", "adil", "keadilan",
        }
        self.negatif_lexicon = {
            # Ekonomi & bisnis
            "rugi", "kerugian", "turun", "penurunan", "menurun", "krisis", "resesi", "inflasi",
            "defisit", "melemah", "pelemahan", "anjlok", "merosot", "kolaps", "bangkrut",
            "kebangkrutan", "phk", "pemutusan hubungan kerja", "pengangguran", "mahal", "kenaikan harga",
            "langka", "kelangkaan", "korupsi", "penyelewengan", "penipuan", "utang", "gagal bayar",
            # Umum / kualitas
            "buruk", "memburuk", "negatif", "gagal", "kegagalan", "sulit", "kesulitan", "susah",
            "masalah", "bermasalah", "kacau", "kekacauan", "rusak", "kerusakan", "hancur",
            "kehancuran", "bencana", "musibah", "tragedi", "kecelakaan", "korban", "meninggal",
            "tewas", "kematian", "cedera", "terluka", "luka-luka", "kritis", "darurat",
            # Konflik / kejahatan
            "konflik", "kerusuhan", "bentrok", "bentrokan", "kekerasan", "kejahatan", "kriminal",
            "pembunuhan", "perampokan", "pencurian", "penipuan", "penculikan", "ancaman",
            "mengancam", "teror", "terorisme", "serangan", "menyerang", "perang", "invasi",
            # Sosial / kesehatan
            "wabah", "pandemi", "penyakit", "sakit", "terinfeksi", "tertular", "kelaparan", "miskin",
            "kemiskinan", "diskriminasi", "eksploitasi", "pelanggaran", "penyalahgunaan",
            # Politik / hukum
            "kalah", "kekalahan", "ditolak", "penolakan", "diblokir", "dibatalkan", "pembatalan",
            "dituntut", "tuntutan", "dipenjara", "hukuman", "sanksi", "pelanggaran hukum",
            "penyalahgunaan wewenang", "manipulasi", "kecurangan", "curang", "protes", "demonstrasi",
            "unjuk rasa", "kritik", "mengkritik", "kecaman", "mengecam", "kontroversi", "skandal",
        }
        logger.info(
            f"SentimentService initialized (lexicon murni, tanpa AI): "
            f"{len(self.positif_lexicon)} kata positif, {len(self.negatif_lexicon)} kata negatif."
        )

    @staticmethod
    def _tokenize(text: str) -> list:
        return re.findall(r"[a-zA-ZÀ-ÿ\-]+", text.lower())

    def analyze_text(self, text: str) -> str:
        if not text or len(text.strip()) < 50:
            return "NEUTRAL"

        tokens = self._tokenize(text)
        if not tokens:
            return "NEUTRAL"

        pos_score = 0.0
        neg_score = 0.0

        for i, word in enumerate(tokens):
            is_positive = word in self.positif_lexicon
            is_negative = word in self.negatif_lexicon
            if not is_positive and not is_negative:
                continue

            weight = 1.0

            # Cek 1-2 kata sebelumnya untuk negasi/penguat.
            window = tokens[max(0, i - 2):i]
            negated = any(w in self.NEGATION_WORDS for w in window)
            intensified = any(w in self.INTENSIFIER_WORDS for w in window)
            if intensified:
                weight = 1.5

            if is_positive:
                if negated:
                    neg_score += weight
                else:
                    pos_score += weight
            elif is_negative:
                if negated:
                    pos_score += weight
                else:
                    neg_score += weight

        # Normalisasi terhadap panjang teks supaya artikel panjang tidak
        # otomatis punya skor mentah lebih besar hanya karena lebih banyak kata.
        length_factor = max(len(tokens), 1) / 100.0
        net_score = (pos_score - neg_score) / max(length_factor, 0.1)

        threshold = 0.5
        if net_score > threshold:
            return "POSITIVE"
        elif net_score < -threshold:
            return "NEGATIVE"
        return "NEUTRAL"


sentiment_service = SentimentService()