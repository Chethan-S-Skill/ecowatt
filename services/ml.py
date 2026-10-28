import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session
import models

logger = logging.getLogger("ecowatt.ml")

def is_ml_enabled(db: Session) -> bool:
    """Checks whether the ML anomaly scoring service is toggled on in settings."""
    setting = db.query(models.Setting).filter(models.Setting.key == "ml_enabled").first()
    if setting and setting.value.lower() in ["false", "0", "no", "disabled"]:
        return False
    return True

def compute_ml_anomaly_scores(
    db: Session,
    building_id: int,
    readings_df: pd.DataFrame
) -> Optional[np.ndarray]:
    """
    Fits an IsolationForest unsupervised anomaly detector on features:
    [kwh, hour, weekday, temperature] (using cached temperature if available, else zero).
    Returns an array of normalized scores from 0.0 to 100.0 (higher = more anomalous).
    Returns None if ML is disabled or insufficient data (< 48 samples).
    Never blocks rule-based results or raises unhandled exceptions.
    """
    if not is_ml_enabled(db):
        return None

    if len(readings_df) < 48:
        return None

    try:
        df = readings_df.copy()
        df["hour"] = df["ts"].dt.hour
        df["weekday"] = df["ts"].dt.weekday

        # Attach temperature from weather cache if present
        weather_records = db.query(models.Weather).all()
        weather_map = {w.ts: w.temp_c for w in weather_records}
        df["temp"] = df["ts"].map(weather_map).fillna(25.0)  # Default fallback 25°C

        features = df[["kwh", "hour", "weekday", "temp"]].values

        # IsolationForest model
        model = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
            n_jobs=1
        )
        model.fit(features)
        
        # decision_function: lower means more anomalous
        raw_scores = model.decision_function(features)
        # Normalize raw scores to 0-100 where higher is more anomalous
        min_s = float(np.min(raw_scores))
        max_s = float(np.max(raw_scores))
        span = max(max_s - min_s, 1e-4)

        # Invert so smallest raw_score becomes 100% anomaly score
        normalized = ((max_s - raw_scores) / span) * 100.0
        return np.round(normalized, 1)

    except Exception as e:
        logger.warning(f"ML IsolationForest scoring skipped for building {building_id}: {e}")
        return None
