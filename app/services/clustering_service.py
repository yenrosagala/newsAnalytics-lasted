"""
Clustering Service
-------------------
Mengelompokkan artikel berita yang membahas isu/peristiwa yang sama menjadi
satu "cerita" (story), lalu menyusun cerita tersebut secara kronologis
menjadi timeline.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.theme import CHART_LAYOUT

try:
    from app.core.logger import get_logger
    logger = get_logger("ClusteringService")
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("ClusteringService")

INDONESIAN_STOPWORDS = [
    "yang", "untuk", "dengan", "dari", "dalam", "pada", "ke", "di", "dan", "atau",
    "ini", "itu", "juga", "akan", "adalah", "sebagai", "oleh", "karena", "namun",
    "tersebut", "para", "agar", "bahwa", "hingga", "saat", "telah", "sudah",
    "belum", "tidak", "bukan", "masih", "lebih", "sangat", "bisa", "dapat",
    "harus", "menjadi", "terhadap", "antara", "melalui", "sebuah", "seorang",
    "sementara", "kata", "menurut", "mengatakan", "ujar", "tutur", "ungkap",
    "kami", "kita", "mereka", "dia", "ia", "nya", "yaitu", "yakni", "serta",
    "maka", "jika", "apabila", "ada", "tak", "pun", "per", "atas", "bagi",
    "usai", "kini", "lalu", "kemudian", "seperti", "beberapa", "banyak",
    "satu", "dua", "tiga", "kata dia", "the", "and", "for", "with", "that",
    "this", "from", "was", "were", "has", "have", "had",
]


class ClusteringService:
    def __init__(self, distance_threshold: float = 0.75, min_df: int = 1):
        self.distance_threshold = distance_threshold
        self.min_df = min_df

    def _prepare_text(self, df: pd.DataFrame, title_col: str, content_col: str) -> pd.Series:
        titles = df[title_col].fillna("").astype(str) if title_col in df.columns else pd.Series([""] * len(df))
        contents = df[content_col].fillna("").astype(str) if content_col in df.columns else pd.Series([""] * len(df))
        return titles + " " + titles + " " + contents.str.slice(0, 1000)

    @staticmethod
    def _pick_representative_title(titles: pd.Series) -> str:
        candidates = [t for t in titles.dropna().astype(str) if t.strip()]
        if not candidates:
            return "Tanpa Judul"
        return min(candidates, key=len)

    def cluster(
        self,
        df: pd.DataFrame,
        title_col: str = "judul",
        content_col: str = "isi_konten",
    ) -> pd.DataFrame:
        result = df.copy().reset_index(drop=True)
        n = len(result)

        if n == 0:
            result["cluster_id"] = pd.Series(dtype=int)
            result["cluster_label"] = pd.Series(dtype=str)
            return result

        if n == 1:
            result["cluster_id"] = [0]
            result["cluster_label"] = [result.iloc[0].get(title_col, "Tanpa Judul")]
            return result

        texts = self._prepare_text(result, title_col, content_col)

        try:
            vectorizer = TfidfVectorizer(
                max_features=5000,
                stop_words=INDONESIAN_STOPWORDS,
                min_df=self.min_df,
                ngram_range=(1, 2),
            )
            tfidf_matrix = vectorizer.fit_transform(texts)

            if tfidf_matrix.shape[1] == 0:
                raise ValueError("Vocabulary kosong setelah filtering stopword.")

            clustering = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=self.distance_threshold,
                metric="cosine",
                linkage="average",
            )
            labels = clustering.fit_predict(tfidf_matrix.toarray())
        except Exception as e:
            logger.warning(f"Clustering gagal ({e}); fallback: setiap artikel jadi cerita sendiri.")
            labels = np.arange(n)

        result["cluster_id"] = labels
        result["cluster_label"] = result.groupby("cluster_id")[title_col].transform(
            self._pick_representative_title
        )
        return result

    def build_cluster_summary(
        self,
        df: pd.DataFrame,
        date_col: str = "waktu_tampilan",
        media_col: str = "media",
    ) -> pd.DataFrame:
        if "cluster_id" not in df.columns or df.empty:
            return pd.DataFrame()

        work = df.copy()
        has_date = date_col in work.columns
        if has_date:
            work[date_col] = pd.to_datetime(work[date_col], errors="coerce")

        agg_dict = {
            "cluster_label": ("cluster_label", "first"),
            "jumlah_artikel": ("cluster_id", "count"),
        }
        if has_date:
            agg_dict["tanggal_mulai"] = (date_col, "min")
            agg_dict["tanggal_akhir"] = (date_col, "max")
        if media_col in work.columns:
            agg_dict["media_terlibat"] = (
                media_col,
                lambda s: ", ".join(sorted(set(s.dropna().astype(str))))[:120],
            )

        summary = work.groupby("cluster_id").agg(**agg_dict).reset_index()
        return summary.sort_values("jumlah_artikel", ascending=False).reset_index(drop=True)

    def build_timeline_fig(
        self,
        df: pd.DataFrame,
        date_col: str = "waktu_tampilan",
        sentiment_col: str = "Sentimen",
        title_col: str = "judul",
        media_col: str = "media",
    ):
        import plotly.express as px

        if df.empty or "cluster_label" not in df.columns:
            return None

        plot_df = df.copy()
        if date_col not in plot_df.columns:
            return None

        plot_df[date_col] = pd.to_datetime(plot_df[date_col], errors="coerce")
        plot_df = plot_df.dropna(subset=[date_col])
        if plot_df.empty:
            return None

        plot_df = plot_df.sort_values(date_col)
        color_col = sentiment_col if sentiment_col in plot_df.columns else None
        hover_cols = {}
        if title_col in plot_df.columns:
            hover_cols[title_col] = True
        if media_col in plot_df.columns:
            hover_cols[media_col] = True

        fig = px.scatter(
            plot_df,
            x=date_col,
            y="cluster_label",
            color=color_col,
            hover_data=hover_cols or None,
            title="Timeline Perkembangan Cerita (Story Timeline)",
        )
        fig.update_traces(marker=dict(size=13, line=dict(width=1, color="white")))
        fig.update_layout(
            **CHART_LAYOUT,
            yaxis_title="Cerita",
            xaxis_title="Tanggal",
            showlegend=color_col is not None,
        )
        fig.update_yaxes(automargin=True)
        return fig


clustering_service = ClusteringService()