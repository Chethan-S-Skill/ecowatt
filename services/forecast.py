from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
import models

def generate_forecast(db: Session, building_id: Optional[int] = None, horizon: str = "24h") -> Dict[str, Any]:
    """
    Generates an hourly load forecast using moving average of the same hour-of-week over the last 4 weeks.
    Strict check: Returns 'not enough history' if under 2 weeks (14 days) of history exist.
    Horizon can be '24h' (24 hours ahead) or '7d' (168 hours ahead).
    """
    # 1. Fetch readings
    query = db.query(models.MeterReading.ts, models.MeterReading.kwh)
    building_name = "Campus Total"
    if building_id:
        b = db.query(models.Building).filter(models.Building.id == building_id).first()
        if b:
            building_name = b.name
        query = query.filter(models.MeterReading.building_id == building_id)

    readings = query.order_by(models.MeterReading.ts.asc()).all()

    if not readings:
        return {
            "building": building_name,
            "horizon": horizon,
            "status": "not_enough_history",
            "message": "No meter reading history found.",
            "points": []
        }

    df = pd.DataFrame([{"ts": r[0], "kwh": r[1]} for r in readings])
    df["ts"] = pd.to_datetime(df["ts"])

    # If campus total, aggregate by hour
    if not building_id:
        df = df.groupby("ts")["kwh"].sum().reset_index()

    df = df.sort_values("ts").reset_index(drop=True)

    min_ts = df["ts"].min()
    max_ts = df["ts"].max()
    days_history = (max_ts - min_ts).days

    if days_history < 14:
        return {
            "building": building_name,
            "horizon": horizon,
            "status": "not_enough_history",
            "message": f"At least 14 days of meter history required for hour-of-week forecasting (found {days_history} days).",
            "points": []
        }

    # Hourly features
    df["weekday"] = df["ts"].dt.weekday
    df["hour"] = df["ts"].dt.hour
    df["hour_of_week"] = df["weekday"] * 24 + df["hour"]

    # Filter to last 4 weeks for moving average
    four_weeks_ago = max_ts - timedelta(days=28)
    df_recent = df[df["ts"] >= four_weeks_ago]

    # Compute mean and standard deviation per hour_of_week
    how_stats = df_recent.groupby("hour_of_week")["kwh"].agg(["mean", "std", "count"]).reset_index()
    how_dict = {}
    for _, row in how_stats.iterrows():
        how = int(row["hour_of_week"])
        mean_val = float(row["mean"])
        std_val = float(row["std"]) if pd.notnull(row["std"]) and row["std"] > 0 else (mean_val * 0.08)
        how_dict[how] = (mean_val, std_val)

    # Generate horizon timestamps
    num_hours = 24 if horizon == "24h" else 168
    future_points = []

    for i in range(1, num_hours + 1):
        target_ts = max_ts + timedelta(hours=i)
        target_how = target_ts.weekday() * 24 + target_ts.hour

        mean_val, std_val = how_dict.get(target_how, (float(df["kwh"].mean()), float(df["kwh"].std() or 1.0)))
        pred_kwh = max(0.0, round(mean_val, 2))
        lower_kwh = max(0.0, round(pred_kwh - (1.28 * std_val), 2))
        upper_kwh = round(pred_kwh + (1.28 * std_val), 2)

        future_points.append({
            "ts": target_ts.isoformat(),
            "predicted_kwh": pred_kwh,
            "lower_bound_kwh": lower_kwh,
            "upper_bound_kwh": upper_kwh
        })

    return {
        "building": building_name,
        "horizon": horizon,
        "status": "success",
        "message": f"Hour-of-week 4-week moving average forecast generated ({num_hours} hours).",
        "points": future_points
    }
