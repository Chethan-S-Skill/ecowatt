from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
import models
import schemas
from auth import require_admin
from services.analytics import calculate_energy_score

router = APIRouter(prefix="/api/buildings", tags=["Buildings"])

@router.get("", response_model=List[schemas.BuildingOut])
def get_buildings(db: Session = Depends(get_db)):
    buildings = db.query(models.Building).order_by(models.Building.name.asc()).all()
    results = []

    for b in buildings:
        # Latest reading for current kW
        latest_reading = db.query(models.MeterReading)\
            .filter(models.MeterReading.building_id == b.id)\
            .order_by(models.MeterReading.ts.desc()).first()
        current_kw = round(latest_reading.kwh, 1) if latest_reading else 0.0

        # Anomalies count
        open_anomalies_count = db.query(models.Anomaly)\
            .filter(models.Anomaly.building_id == b.id, models.Anomaly.status == "open")\
            .count()

        # Total vs wasted kwh over last 28 days for score
        total_kwh = db.query(func.sum(models.MeterReading.kwh))\
            .filter(models.MeterReading.building_id == b.id).scalar() or 0.0

        total_wasted = db.query(func.sum(models.Anomaly.wasted_kwh))\
            .filter(models.Anomaly.building_id == b.id, models.Anomaly.status == "open").scalar() or 0.0

        score = calculate_energy_score(float(total_kwh), float(total_wasted))

        b_out = schemas.BuildingOut(
            id=b.id,
            name=b.name,
            type=b.type,
            is_24h=b.is_24h,
            peak_kw=b.peak_kw,
            idle_pct=b.idle_pct,
            current_kw=current_kw,
            energy_score=score,
            anomaly_count=open_anomalies_count
        )
        results.append(b_out)

    return results

@router.post("", response_model=schemas.BuildingOut, status_code=status.HTTP_201_CREATED)
def create_building(
    b_in: schemas.BuildingCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin)
):
    existing = db.query(models.Building).filter(models.Building.name.ilike(b_in.name.strip())).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Building with name '{b_in.name}' already exists."
        )

    building = models.Building(
        name=b_in.name.strip(),
        type=b_in.type,
        is_24h=b_in.is_24h,
        peak_kw=b_in.peak_kw,
        idle_pct=b_in.idle_pct
    )
    db.add(building)
    db.commit()
    db.refresh(building)

    return schemas.BuildingOut(
        id=building.id,
        name=building.name,
        type=building.type,
        is_24h=building.is_24h,
        peak_kw=building.peak_kw,
        idle_pct=building.idle_pct,
        current_kw=0.0,
        energy_score=100.0,
        anomaly_count=0
    )
