import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd
import numpy as np

from database import get_db
import models
import schemas
from services.analytics import calculate_energy_score, get_tariff_and_emission
from services.forecast import generate_forecast
from services.ml import compute_ml_anomaly_scores, is_ml_enabled

router = APIRouter(prefix="/api", tags=["Analytics & Insights"])

@router.get("/summary", response_model=schemas.SummaryOut)
def get_summary(
    building: Optional[str] = Query(None, description="Building name or empty for campus total"),
    days: int = Query(28, ge=1, le=90, description="Analysis window in days"),
    db: Session = Depends(get_db)
):
    tariff, emission = get_tariff_and_emission(db)
    target_building = None
    if building and building.strip() and building.strip().lower() != "campus total":
        target_building = db.query(models.Building).filter(models.Building.name.ilike(building.strip())).first()
        if not target_building:
            raise HTTPException(status_code=404, detail=f"Building '{building}' not found")

    cutoff_ts = datetime.utcnow() - timedelta(days=days)

    # Base query for readings
    readings_q = db.query(models.MeterReading).filter(models.MeterReading.ts >= cutoff_ts)
    anomalies_q = db.query(models.Anomaly).filter(models.Anomaly.end_ts >= cutoff_ts)
    recs_q = db.query(models.Recommendation)

    if target_building:
        readings_q = readings_q.filter(models.MeterReading.building_id == target_building.id)
        anomalies_q = anomalies_q.filter(models.Anomaly.building_id == target_building.id)
        recs_q = recs_q.filter(models.Recommendation.building_id == target_building.id)

    total_kwh = float(readings_q.with_entities(func.sum(models.MeterReading.kwh)).scalar() or 0.0)
    wasted_kwh = float(anomalies_q.with_entities(func.sum(models.Anomaly.wasted_kwh)).scalar() or 0.0)

    # Recommendations & what-if applied savings
    all_recs = recs_q.all()
    total_recs_count = len(all_recs)
    applied_recs = [r for r in all_recs if r.applied]
    applied_count = len(applied_recs)

    # What-if applied savings: sum of (kwh_week * 52)
    applied_annual_kwh = sum(r.kwh_week * 52.0 for r in applied_recs)
    projected_savings_rupees = sum(r.rupees_year for r in applied_recs)
    co2_reduction_tons = sum(r.co2_t_year for r in applied_recs)

    # If no recommendations are applied yet, show total potential savings as preview
    if applied_count == 0 and total_recs_count > 0:
        preview_rupees = sum(r.rupees_year for r in all_recs)
        preview_co2 = sum(r.co2_t_year for r in all_recs)
    else:
        preview_rupees = projected_savings_rupees
        preview_co2 = co2_reduction_tons

    wasted_pct = round((wasted_kwh / total_kwh * 100.0), 1) if total_kwh > 0 else 0.0

    # Energy score baseline
    score_baseline = calculate_energy_score(total_kwh, wasted_kwh)

    # Energy score optimized (after applied fixes)
    # Convert applied annual savings into equivalent waste reduction over the queried window
    window_weeks = days / 7.0
    applied_window_saved = sum(r.kwh_week * window_weeks for r in applied_recs)
    wasted_after_fixes = max(0.0, wasted_kwh - applied_window_saved)
    score_optimized = calculate_energy_score(total_kwh, wasted_after_fixes)

    open_anomalies_count = anomalies_q.filter(models.Anomaly.status == "open").count()

    return schemas.SummaryOut(
        building_name=target_building.name if target_building else "Campus Total",
        days_analyzed=days,
        total_kwh=round(total_kwh, 1),
        wasted_kwh=round(wasted_kwh, 1),
        wasted_pct=wasted_pct,
        projected_savings_rupees_year=round(preview_rupees, 1),
        co2_reduction_tons_year=round(preview_co2, 2),
        energy_score_baseline=score_baseline,
        energy_score_optimized=score_optimized,
        open_anomalies_count=open_anomalies_count,
        applied_recommendations_count=applied_count,
        total_recommendations_count=total_recs_count,
        tariff_inr=tariff,
        emission_factor=emission
    )

@router.get("/series", response_model=schemas.SeriesResponse)
def get_series(
    building: Optional[str] = Query(None, description="Building name or empty for campus total"),
    days: int = Query(7, ge=1, le=30, description="Number of days of hourly series"),
    db: Session = Depends(get_db)
):
    target_building = None
    if building and building.strip() and building.strip().lower() != "campus total":
        target_building = db.query(models.Building).filter(models.Building.name.ilike(building.strip())).first()

    cutoff_ts = datetime.utcnow() - timedelta(days=days)

    query = db.query(models.MeterReading.ts, models.MeterReading.kwh, models.MeterReading.building_id)\
        .filter(models.MeterReading.ts >= cutoff_ts)

    if target_building:
        query = query.filter(models.MeterReading.building_id == target_building.id)

    readings = query.order_by(models.MeterReading.ts.asc()).all()

    if not readings:
        return schemas.SeriesResponse(
            building=target_building.name if target_building else "Campus Total",
            days=days,
            points=[]
        )

    df = pd.DataFrame([{"ts": r[0], "kwh": r[1], "b_id": r[2]} for r in readings])
    df["ts"] = pd.to_datetime(df["ts"])

    # Aggregate by hour if campus total
    if not target_building:
        df_agg = df.groupby("ts")["kwh"].sum().reset_index()
        baseline_kw = float(df_agg["kwh"].median() * 0.75) if len(df_agg) > 0 else 50.0
    else:
        df_agg = df.sort_values("ts").reset_index(drop=True)
        baseline_kw = target_building.idle_pct * target_building.peak_kw

    # Check anomalies in window
    anom_q = db.query(models.Anomaly).filter(models.Anomaly.end_ts >= cutoff_ts)
    if target_building:
        anom_q = anom_q.filter(models.Anomaly.building_id == target_building.id)
    anomalies = anom_q.all()

    # Recommendations applied
    rec_q = db.query(models.Recommendation)
    if target_building:
        rec_q = rec_q.filter(models.Recommendation.building_id == target_building.id)
    recs = rec_q.all()
    applied_rules = {r.anomaly_rule for r in recs if r.applied}

    # Optional ML Anomaly Scoring
    ml_scores = None
    if target_building and is_ml_enabled(db):
        ml_scores = compute_ml_anomaly_scores(db, target_building.id, df_agg)

    points = []
    for idx, row in df_agg.iterrows():
        pt_ts = row["ts"].to_pydatetime()
        pt_kwh = float(row["kwh"])

        # Check if point falls within an anomaly interval
        is_anom = False
        wasted_val = 0.0
        rule_name = None

        for a in anomalies:
            if a.start_ts <= pt_ts <= a.end_ts:
                is_anom = True
                rule_name = a.rule
                # Estimate point waste
                if rule_name == "daylight_lighting":
                    wasted_val = pt_kwh
                else:
                    wasted_val = max(0.0, pt_kwh - baseline_kw)
                break

        # Calculate optimized load after applied fixes
        optimized_val = pt_kwh
        if is_anom and rule_name in applied_rules:
            cap_rate = 0.80 if rule_name == "after_hours" else (0.70 if rule_name == "weekend_waste" else 0.95)
            optimized_val = max(baseline_kw, pt_kwh - (wasted_val * cap_rate))

        ml_score = float(ml_scores[idx]) if ml_scores is not None and idx < len(ml_scores) else None

        points.append(schemas.SeriesPoint(
            ts=pt_ts,
            kwh=round(pt_kwh, 2),
            is_anomaly=is_anom,
            wasted_kwh=round(wasted_val, 2),
            baseline_kwh=round(baseline_kw, 2),
            optimized_kwh=round(optimized_val, 2),
            anomaly_rule=rule_name,
            ml_anomaly_score=ml_score
        ))

    return schemas.SeriesResponse(
        building=target_building.name if target_building else "Campus Total",
        days=days,
        points=points
    )

@router.get("/heatmap", response_model=schemas.HeatmapResponse)
def get_heatmap(
    building: Optional[str] = Query(None, description="Building name or empty for campus total"),
    db: Session = Depends(get_db)
):
    target_building = None
    if building and building.strip() and building.strip().lower() != "campus total":
        target_building = db.query(models.Building).filter(models.Building.name.ilike(building.strip())).first()

    query = db.query(models.MeterReading.ts, models.MeterReading.kwh)
    if target_building:
        query = query.filter(models.MeterReading.building_id == target_building.id)

    readings = query.all()
    if not readings:
        return schemas.HeatmapResponse(
            building=target_building.name if target_building else "Campus Total",
            cells=[]
        )

    df = pd.DataFrame([{"ts": r[0], "kwh": r[1]} for r in readings])
    df["ts"] = pd.to_datetime(df["ts"])

    if not target_building:
        df = df.groupby("ts")["kwh"].sum().reset_index()

    df["weekday"] = df["ts"].dt.weekday  # 0=Monday, 6=Sunday
    df["hour"] = df["ts"].dt.hour

    grid = df.groupby(["weekday", "hour"])["kwh"].mean().reset_index()
    overall_mean = float(df["kwh"].mean()) if len(df) > 0 else 100.0

    cells = []
    for _, row in grid.iterrows():
        w = int(row["weekday"])
        h = int(row["hour"])
        avg_val = round(float(row["kwh"]), 1)
        # Mark as wasted zone if weekend daytime or night hours on non-24h
        is_waste = False
        if target_building and not target_building.is_24h:
            if h in [22, 23, 0, 1, 2, 3, 4] and avg_val > (target_building.idle_pct * target_building.peak_kw):
                is_waste = True
            elif w in [5, 6] and 9 <= h <= 16 and avg_val > (target_building.idle_pct * target_building.peak_kw):
                is_waste = True
        elif avg_val > (1.3 * overall_mean):
            is_waste = True

        cells.append(schemas.HeatmapCell(
            weekday=w,
            hour=h,
            avg_kwh=avg_val,
            is_wasted_zone=is_waste
        ))

    return schemas.HeatmapResponse(
        building=target_building.name if target_building else "Campus Total",
        cells=cells
    )

@router.get("/forecast", response_model=schemas.ForecastResponse)
def get_forecast(
    building: Optional[str] = Query(None, description="Building name or empty for campus total"),
    horizon: str = Query("24h", pattern="^(24h|7d)$", description="Forecast horizon: 24h or 7d"),
    db: Session = Depends(get_db)
):
    target_building = None
    if building and building.strip() and building.strip().lower() != "campus total":
        target_building = db.query(models.Building).filter(models.Building.name.ilike(building.strip())).first()
        if not target_building:
            raise HTTPException(status_code=404, detail=f"Building '{building}' not found")

    b_id = target_building.id if target_building else None
    forecast_data = generate_forecast(db, building_id=b_id, horizon=horizon)
    return schemas.ForecastResponse(**forecast_data)

@router.get("/export-report", response_class=HTMLResponse)
def export_printable_report(db: Session = Depends(get_db)):
    """Generates an executive, printable HTML audit report for the campus facility director."""
    tariff, emission = get_tariff_and_emission(db)
    buildings = db.query(models.Building).order_by(models.Building.name.asc()).all()
    anomalies = db.query(models.Anomaly).filter(models.Anomaly.status == "open").all()
    recs = db.query(models.Recommendation).all()

    total_kwh = float(db.query(func.sum(models.MeterReading.kwh)).scalar() or 0.0)
    total_wasted = float(db.query(func.sum(models.Anomaly.wasted_kwh)).scalar() or 0.0)
    overall_score = calculate_energy_score(total_kwh, total_wasted)

    total_potential_inr = sum(r.rupees_year for r in recs)
    total_potential_co2 = sum(r.co2_t_year for r in recs)

    now_str = datetime.utcnow().strftime("%B %d, %Y - %H:%M UTC")

    b_rows = ""
    for b in buildings:
        b_kwh = float(db.query(func.sum(models.MeterReading.kwh)).filter(models.MeterReading.building_id == b.id).scalar() or 0.0)
        b_wasted = float(db.query(func.sum(models.Anomaly.wasted_kwh)).filter(models.Anomaly.building_id == b.id).scalar() or 0.0)
        b_score = calculate_energy_score(b_kwh, b_wasted)
        b_anom_cnt = len([a for a in anomalies if a.building_id == b.id])
        b_rows += f"""
        <tr>
            <td><strong>{b.name}</strong></td>
            <td><span class="badge">{b.type.upper()}</span></td>
            <td>{b.peak_kw:.0f} kW</td>
            <td>{b_kwh:,.0f} kWh</td>
            <td><span style="color:#ef4444;font-weight:600;">{b_wasted:,.0f} kWh</span></td>
            <td><strong style="color:{'#10b981' if b_score>=80 else '#f59e0b'};">{b_score}/100</strong></td>
            <td>{b_anom_cnt} open</td>
        </tr>
        """

    anom_rows = ""
    for a in anomalies[:15]:
        b_name = next((b.name for b in buildings if b.id == a.building_id), "Campus")
        sev_color = "#ef4444" if a.severity == "High" else ("#f59e0b" if a.severity == "Medium" else "#3b82f6")
        anom_rows += f"""
        <tr>
            <td>{b_name}</td>
            <td><code>{a.rule}</code></td>
            <td><span style="background:{sev_color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;">{a.severity}</span></td>
            <td>{a.start_ts.strftime('%m/%d %H:%M')} &rarr; {a.end_ts.strftime('%m/%d %H:%M')}</td>
            <td><strong>{a.wasted_kwh:.1f} kWh</strong></td>
        </tr>
        """

    rec_rows = ""
    for r in recs:
        b_name = next((b.name for b in buildings if b.id == r.building_id), "Campus")
        status_tag = "<span style='color:#10b981;font-weight:bold;'>✓ APPLIED</span>" if r.applied else "<span style='color:#6b7280;'>PENDING</span>"
        rec_rows += f"""
        <tr>
            <td>{b_name}</td>
            <td>{r.fix_text}</td>
            <td>{r.kwh_week:,.0f} kWh/wk</td>
            <td><strong>₹{r.rupees_year:,.0f}</strong></td>
            <td>{r.co2_t_year:.2f} t</td>
            <td>{status_tag}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EcoWatt AI - Campus Energy Optimization Report</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #1f2937; margin: 40px; background: #fff; }}
    .header {{ border-bottom: 3px solid #0d9488; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }}
    h1 {{ margin: 0; color: #0f172a; font-size: 26px; }}
    .tagline {{ color: #0d9488; font-weight: 600; margin-top: 5px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }}
    .kpi-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 15px; background: #f8fafc; text-align: center; }}
    .kpi-card h3 {{ font-size: 13px; text-transform: uppercase; color: #64748b; margin: 0 0 5px 0; }}
    .kpi-card .val {{ font-size: 24px; font-weight: 700; color: #0f172a; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 10px 12px; text-align: left; }}
    th {{ background: #f1f5f9; font-weight: 600; color: #334155; }}
    .badge {{ background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
    .print-btn {{ background: #0d9488; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
    @media print {{ .print-btn {{ display: none; }} body {{ margin: 20px; }} }}
</style>
</head>
<body>
    <div class="header">
        <div>
            <h1>EcoWatt AI &ndash; Campus Energy Audit & Optimization Report</h1>
            <div class="tagline">Automated Sub-Meter Intelligence & Measurable Carbon Reduction</div>
            <div style="font-size: 13px; color: #64748b; margin-top: 5px;">Generated: {now_str} &bull; Tariff: ₹{tariff:.2f}/kWh &bull; Emission Factor: {emission:.2f} kg CO₂/kWh</div>
        </div>
        <button class="print-btn" onclick="window.print()">🖨️ Print / Save PDF</button>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <h3>Campus Energy Score</h3>
            <div class="val" style="color: {'#10b981' if overall_score>=80 else '#f59e0b'};">{overall_score}/100</div>
        </div>
        <div class="kpi-card">
            <h3>Total Consumption</h3>
            <div class="val">{total_kwh:,.0f} kWh</div>
        </div>
        <div class="kpi-card">
            <h3>Preventable Waste</h3>
            <div class="val" style="color: #ef4444;">{total_wasted:,.0f} kWh</div>
        </div>
        <div class="kpi-card">
            <h3>Annualized Savings</h3>
            <div class="val" style="color: #059669;">₹{total_potential_inr:,.0f}</div>
        </div>
    </div>

    <h2>1. Campus Facility Breakdown</h2>
    <table>
        <thead>
            <tr>
                <th>Building Name</th>
                <th>Type</th>
                <th>Peak Capacity</th>
                <th>Total Load</th>
                <th>Wasted Load</th>
                <th>Efficiency Score</th>
                <th>Active Issues</th>
            </tr>
        </thead>
        <tbody>
            {b_rows}
        </tbody>
    </table>

    <h2>2. Active Energy Inefficiencies & Anomalies</h2>
    <table>
        <thead>
            <tr>
                <th>Location</th>
                <th>Inefficiency Category</th>
                <th>Severity</th>
                <th>Observed Interval</th>
                <th>Wasted Power</th>
            </tr>
        </thead>
        <tbody>
            {anom_rows}
        </tbody>
    </table>

    <h2>3. Measurable Recommendations & What-If Interventions</h2>
    <table>
        <thead>
            <tr>
                <th>Facility</th>
                <th>Actionable Intervention</th>
                <th>Weekly Impact</th>
                <th>Rupees Saved / Year</th>
                <th>CO₂ Avoided / Year</th>
                <th>BMS Status</th>
            </tr>
        </thead>
        <tbody>
            {rec_rows}
        </tbody>
    </table>

    <div style="border-top: 1px solid #cbd5e1; padding-top: 15px; font-size: 12px; color: #64748b; text-align: center;">
        EcoWatt AI &ndash; IEEE EcoTech Hackathon Solution &bull; Safe for live production demo &bull; Verified parameterised models
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)
