"""
Predictive Intelligence Service
=================================
Fase 6 roadmap: Trend detection, forecasting, anomaly detection, alerts.
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from app.core.logger import get_logger
    logger = get_logger("PredictiveService")
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("PredictiveService")

DEFAULT_ANOMALY_WINDOW = 7
DEFAULT_ANOMALY_THRESHOLD = 2.5
DEFAULT_FORECAST_HORIZON_DAYS = 7
DEFAULT_TREND_WINDOW_DAYS = 7
TREND_STABLE_THRESHOLD_PCT = 15.0


def build_daily_volume_series(
    df: pd.DataFrame, date_col: str = "waktu_tampilan"
) -> pd.Series:
    if df.empty or date_col not in df.columns:
        return pd.Series(dtype=int)

    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    if work.empty:
        return pd.Series(dtype=int)

    daily = work.groupby(work[date_col].dt.date).size()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()

    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)
    daily.index.name = "tanggal"
    return daily


def classify_trend(
    daily_series: pd.Series,
    recent_days: int = DEFAULT_TREND_WINDOW_DAYS,
    prior_days: int = DEFAULT_TREND_WINDOW_DAYS,
) -> Dict:
    if daily_series.empty or len(daily_series) < 2:
        return {"direction": "Tidak Cukup Data", "pct_change": 0.0, "recent_avg": 0.0, "prior_avg": 0.0}

    recent = daily_series.iloc[-recent_days:]
    prior_window = daily_series.iloc[-(recent_days + prior_days):-recent_days]

    recent_avg = float(recent.mean()) if len(recent) else 0.0
    prior_avg = float(prior_window.mean()) if len(prior_window) else recent_avg

    if prior_avg == 0:
        pct_change = 100.0 if recent_avg > 0 else 0.0
    else:
        pct_change = round((recent_avg - prior_avg) / prior_avg * 100, 1)

    if len(prior_window) == 0:
        direction = "Tidak Cukup Data"
    elif pct_change > TREND_STABLE_THRESHOLD_PCT:
        direction = "Naik"
    elif pct_change < -TREND_STABLE_THRESHOLD_PCT:
        direction = "Turun"
    else:
        direction = "Stabil"

    return {
        "direction": direction,
        "pct_change": pct_change,
        "recent_avg": round(recent_avg, 1),
        "prior_avg": round(prior_avg, 1),
    }


def forecast_linear(
    daily_series: pd.Series, horizon_days: int = DEFAULT_FORECAST_HORIZON_DAYS
) -> Optional[Dict]:
    if daily_series.empty or len(daily_series) < 5:
        return None

    from sklearn.linear_model import LinearRegression

    y = daily_series.values.astype(float)
    X = np.arange(len(y)).reshape(-1, 1)

    model = LinearRegression()
    model.fit(X, y)

    residuals = y - model.predict(X)
    residual_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

    future_X = np.arange(len(y), len(y) + horizon_days).reshape(-1, 1)
    forecast_values = model.predict(future_X)
    forecast_values = np.clip(forecast_values, 0, None)

    last_date = daily_series.index[-1]
    forecast_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon_days, freq="D")

    return {
        "forecast_dates": forecast_dates,
        "forecast_values": forecast_values,
        "lower_band": np.clip(forecast_values - 1.96 * residual_std, 0, None),
        "upper_band": forecast_values + 1.96 * residual_std,
        "slope_per_day": float(model.coef_[0]),
        "residual_std": residual_std,
    }


def detect_anomalies_robust_zscore(
    daily_series: pd.Series,
    window: int = DEFAULT_ANOMALY_WINDOW,
    threshold: float = DEFAULT_ANOMALY_THRESHOLD,
) -> pd.DataFrame:
    if daily_series.empty or len(daily_series) < window + 1:
        return pd.DataFrame(columns=["tanggal", "nilai", "rolling_median", "robust_z_score", "is_anomaly", "arah"])

    values = daily_series.values.astype(float)
    n = len(values)
    rows = []

    for i in range(n):
        start = max(0, i - window)
        window_vals = values[start:i]
        if len(window_vals) < max(3, window // 2):
            rows.append((daily_series.index[i], values[i], np.nan, 0.0, False, "-"))
            continue

        med = np.median(window_vals)
        mad = np.median(np.abs(window_vals - med))
        scale = mad * 1.4826 if mad > 0 else max(1.0, med * 0.2)
        z = (values[i] - med) / scale

        is_anomaly = bool(abs(z) >= threshold)
        arah = "Lonjakan" if z > 0 else "Penurunan" if is_anomaly else "-"
        rows.append((daily_series.index[i], values[i], med, round(float(z), 2), is_anomaly, arah))

    return pd.DataFrame(rows, columns=["tanggal", "nilai", "rolling_median", "robust_z_score", "is_anomaly", "arah"])


def generate_alerts(
    keyword: str,
    trend_info: Dict,
    anomalies_df: pd.DataFrame,
    max_anomaly_alerts: int = 3,
) -> List[Dict]:
    alerts = []

    if not anomalies_df.empty:
        recent_anomalies = anomalies_df[anomalies_df["is_anomaly"]].tail(max_anomaly_alerts)
        for _, row in recent_anomalies.iterrows():
            severity = "Tinggi" if abs(row["robust_z_score"]) >= DEFAULT_ANOMALY_THRESHOLD * 1.5 else "Sedang"
            tgl_str = row["tanggal"].strftime("%d %b %Y") if pd.notnull(row["tanggal"]) else "-"
            alerts.append({
                "severity": severity,
                "type": "anomaly",
                "message": (
                    f"{row['arah']} volume berita untuk '{keyword}' pada {tgl_str}: "
                    f"{int(row['nilai'])} artikel (normal sekitar {row['rolling_median']:.0f})."
                ),
            })

    direction = trend_info.get("direction")
    if direction in ("Naik", "Turun"):
        severity = "Sedang" if abs(trend_info.get("pct_change", 0)) >= 50 else "Rendah"
        arrow = "📈" if direction == "Naik" else "📉"
        alerts.append({
            "severity": severity,
            "type": "trend",
            "message": (
                f"{arrow} Tren volume berita '{keyword}' {direction.lower()} "
                f"{abs(trend_info.get('pct_change', 0)):.0f}% dibanding periode sebelumnya "
                f"({trend_info.get('prior_avg')} -> {trend_info.get('recent_avg')} artikel/hari)."
            ),
        })

    return alerts