import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from config import settings
from services.alerts import send_high_severity_alert

logger = logging.getLogger("ecowatt.analytics")

CAPTURE_RATES = {
    "after_hours": 0.80,
    "weekend_waste": 0.70,
    "daylight_lighting": 0.95,
    "spike": 0.50
}

FIX_TEXTS = {
    "after_hours": "Implement automated night setbacks and smart sub-meter relays to cut inactive computer lab & classroom vampire loads from 22:00 to 05:00.",
    "weekend_waste": "Enforce weekend HVAC and lighting lockouts on academic and admin blocks; switch to occupancy sensors.",
    "daylight_lighting": "Install photocell lux sensors and astronomical timer overrides on campus pathway lighting circuits to ensure shut-off by 07:00.",
    "spike": "Deploy peak demand shaving protocols and stagger chiller compressor staging during afternoon thermal peaks."
}

def get_tariff_and_emission(db: Session) -> Tuple[float, float]:
    """Retrieves tariff (INR/kWh) and emission factor (kg CO2/kWh) from settings or defaults."""
    tariff_row = db.query(models.Setting).filter(models.Setting.key == "tariff_inr").first()
    tariff = float(tariff_row.value) if tariff_row else settings.DEFAULT_TARIFF_INR

    emission_row = db.query(models.Setting).filter(models.Setting.key == "emission_factor").first()
    emission = float(emission_row.value) if emission_row else settings.DEFAULT_EMISSION_FACTOR

    return tariff, emission

def calculate_energy_score(total_kwh: float, wasted_kwh: float) -> float:
    """
    Computes building Energy Score from 0 to 100:
    Formula: 100 - (wasted_kwh / total_kwh * 400), clamped [0, 100].
    """
    if total_kwh <= 0:
        return 100.0
    score = 100.0 - (wasted_kwh / total_kwh * 400.0)
    return round(float(np.clip(score, 0.0, 100.0)), 1)

def run_analytics_for_buildings(db: Session, building_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Executes rule-based energy waste analytics for the specified buildings (or all if None).
    Detects after-hours waste, weekend daytime waste, daylight lighting, and robust z-score spikes.
    Groups consecutive hours into single anomalies and updates recommendations with savings maths.
    """
    if not building_ids:
        buildings = db.query(models.Building).all()
    else:
        buildings = db.query(models.Building).filter(models.Building.id.in_(building_ids)).all()

    tariff, emission = get_tariff_and_emission(db)
    summary_results = {
        "buildings_processed": len(buildings),
        "new_anomalies": 0,
        "high_alerts_sent": 0
    }

    for b in buildings:
        # Load readings for this building
        readings = db.query(models.MeterReading)\
            .filter(models.MeterReading.building_id == b.id)\
            .order_by(models.MeterReading.ts.asc()).all()

        if not readings:
            continue

        df = pd.DataFrame([{"id": r.id, "ts": r.ts, "kwh": r.kwh} for r in readings])
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts").reset_index(drop=True)

        idle_target = b.idle_pct * b.peak_kw
        df["hour"] = df["ts"].dt.hour
        df["weekday"] = df["ts"].dt.weekday  # 0=Monday, 6=Sunday
        df["hour_of_week"] = df["weekday"] * 24 + df["hour"]

        # 1. Baseline median & MAD per hour_of_week for spike detection
        stats = df.groupby("hour_of_week")["kwh"].agg(["median", lambda x: np.median(np.abs(x - np.median(x)))])
        stats.columns = ["how_median", "how_mad"]
        df = df.merge(stats, on="hour_of_week", how="left")
        df["robust_z"] = 0.6745 * (df["kwh"] - df["how_median"]) / (df["how_mad"] + 1e-5)

        # Flag arrays
        df["flag_after_hours"] = False
        df["flag_weekend_waste"] = False
        df["flag_daylight_lighting"] = False
        df["flag_spike"] = False
        df["wasted_kwh"] = 0.0

        # Rule 1: After-hours baseload (22:00-04:59, non-24h buildings)
        if not b.is_24h:
            cond_ah = (df["hour"].isin([22, 23, 0, 1, 2, 3, 4])) & (df["kwh"] > idle_target)
            df.loc[cond_ah, "flag_after_hours"] = True

        # Rule 2: Weekend daytime waste (09:00-16:59, Sat/Sun, academic|lab|admin)
        if not b.is_24h and b.type in ["academic", "lab", "admin"]:
            cond_we = (df["weekday"].isin([5, 6])) & (df["hour"].between(9, 16)) & (df["kwh"] > idle_target)
            df.loc[cond_we, "flag_weekend_waste"] = True

        # Rule 3: Daylight lighting (07:00-08:59, lighting type)
        if b.type == "lighting":
            cond_dl = (df["hour"].isin([7, 8])) & (df["kwh"] > (0.05 * b.peak_kw))
            df.loc[cond_dl, "flag_daylight_lighting"] = True

        # Rule 4: Spikes (kwh > median * 1.25 AND robust_z > 3.0)
        cond_sp = (df["kwh"] > (df["how_median"] * 1.25)) & (df["robust_z"] > 3.0)
        df.loc[cond_sp, "flag_spike"] = True

        # Assign wasted kWh based on priority
        for idx, row in df.iterrows():
            if row["flag_daylight_lighting"]:
                df.at[idx, "wasted_kwh"] = row["kwh"]
            elif row["flag_after_hours"] or row["flag_weekend_waste"]:
                df.at[idx, "wasted_kwh"] = max(0.0, row["kwh"] - idle_target)
            elif row["flag_spike"]:
                df.at[idx, "wasted_kwh"] = max(0.0, row["kwh"] - row["how_median"])

        # Group consecutive hours into distinct anomaly episodes
        detected_anomalies = []
        for rule_name, flag_col in [
            ("after_hours", "flag_after_hours"),
            ("weekend_waste", "flag_weekend_waste"),
            ("daylight_lighting", "flag_daylight_lighting"),
            ("spike", "flag_spike")
        ]:
            flagged_indices = df[df[flag_col]].index.tolist()
            if not flagged_indices:
                continue

            # Group contiguous row indices where ts is consecutive hours
            clusters = []
            current_cluster = [flagged_indices[0]]

            for prev_idx, curr_idx in zip(flagged_indices[:-1], flagged_indices[1:]):
                prev_ts = df.at[prev_idx, "ts"]
                curr_ts = df.at[curr_idx, "ts"]
                if (curr_ts - prev_ts) <= timedelta(hours=1):
                    current_cluster.append(curr_idx)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [curr_idx]
            clusters.append(current_cluster)

            for cluster in clusters:
                cluster_df = df.loc[cluster]
                start_ts = cluster_df["ts"].min().to_pydatetime()
                end_ts = cluster_df["ts"].max().to_pydatetime()
                total_wasted = float(cluster_df["wasted_kwh"].sum())

                # Determine Severity: High above 600 kWh/week, Medium above 250, else Low
                if total_wasted >= 600.0:
                    severity = "High"
                elif total_wasted >= 250.0:
                    severity = "Medium"
                else:
                    severity = "Low"

                evidence_dict = {
                    "rule": rule_name,
                    "building_type": b.type,
                    "peak_kw": b.peak_kw,
                    "idle_target_kw": round(idle_target, 2),
                    "mean_load_kw": round(float(cluster_df["kwh"].mean()), 2),
                    "duration_hours": len(cluster),
                    "max_spike_z": round(float(cluster_df["robust_z"].max()), 2) if "robust_z" in cluster_df else 0.0
                }

                detected_anomalies.append({
                    "building_id": b.id,
                    "building_name": b.name,
                    "rule": rule_name,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "wasted_kwh": round(total_wasted, 2),
                    "severity": severity,
                    "evidence": json.dumps(evidence_dict)
                })

        # Sync anomalies in database (avoid duplicate open anomalies for the exact start_ts/rule)
        for anom in detected_anomalies:
            existing = db.query(models.Anomaly).filter(
                models.Anomaly.building_id == anom["building_id"],
                models.Anomaly.rule == anom["rule"],
                models.Anomaly.start_ts == anom["start_ts"]
            ).first()

            if not existing:
                new_anomaly = models.Anomaly(
                    building_id=anom["building_id"],
                    rule=anom["rule"],
                    start_ts=anom["start_ts"],
                    end_ts=anom["end_ts"],
                    wasted_kwh=anom["wasted_kwh"],
                    severity=anom["severity"],
                    evidence=anom["evidence"],
                    status="open",
                    created_at=datetime.utcnow()
                )
                db.add(new_anomaly)
                db.flush()
                summary_results["new_anomalies"] += 1

                # If High severity, trigger email alert!
                if anom["severity"] == "High":
                    sent = send_high_severity_alert(
                        building_name=anom["building_name"],
                        rule=anom["rule"],
                        start_ts=anom["start_ts"].strftime("%Y-%m-%d %H:%M"),
                        end_ts=anom["end_ts"].strftime("%Y-%m-%d %H:%M"),
                        wasted_kwh=anom["wasted_kwh"],
                        evidence=anom["evidence"]
                    )
                    if sent:
                        summary_results["high_alerts_sent"] += 1

        # Recommendations generation per active rule for this building
        # Aggregate weekly waste rate over historical window
        days_covered = max(1, (df["ts"].max() - df["ts"].min()).days)
        weeks_covered = max(0.14, days_covered / 7.0)

        for rule_name, cap_rate in CAPTURE_RATES.items():
            rule_anomalies = [a for a in detected_anomalies if a["rule"] == rule_name]
            if not rule_anomalies:
                continue

            total_rule_wasted = sum(a["wasted_kwh"] for a in rule_anomalies)
            weekly_wasted = total_rule_wasted / weeks_covered
            kwh_week = round(weekly_wasted * cap_rate, 2)
            rupees_year = round(kwh_week * 52.0 * tariff, 2)
            co2_t_year = round((kwh_week * 52.0 * emission) / 1000.0, 2)

            existing_rec = db.query(models.Recommendation).filter(
                models.Recommendation.building_id == b.id,
                models.Recommendation.anomaly_rule == rule_name
            ).first()

            if existing_rec:
                # Update figures while preserving user's applied toggle state
                existing_rec.kwh_week = kwh_week
                existing_rec.rupees_year = rupees_year
                existing_rec.co2_t_year = co2_t_year
                existing_rec.fix_text = FIX_TEXTS.get(rule_name, existing_rec.fix_text)
            else:
                new_rec = models.Recommendation(
                    building_id=b.id,
                    anomaly_rule=rule_name,
                    fix_text=FIX_TEXTS.get(rule_name, "Optimize equipment operating schedule."),
                    capture_rate=cap_rate,
                    kwh_week=kwh_week,
                    rupees_year=rupees_year,
                    co2_t_year=co2_t_year,
                    applied=False
                )
                db.add(new_rec)

    db.commit()
    return summary_results
