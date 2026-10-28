from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from auth import get_current_user

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies"])

@router.get("", response_model=List[schemas.AnomalyOut])
def get_anomalies(
    building: Optional[str] = Query(None, description="Filter by building name"),
    status: Optional[str] = Query(None, description="Filter by status: open or resolved"),
    severity: Optional[str] = Query(None, description="Filter by severity: High, Medium, Low"),
    db: Session = Depends(get_db)
):
    query = db.query(models.Anomaly).join(models.Building)

    if building and building.strip() and building.strip().lower() != "campus total":
        query = query.filter(models.Building.name.ilike(building.strip()))

    if status and status.strip():
        query = query.filter(models.Anomaly.status == status.strip().lower())

    if severity and severity.strip():
        query = query.filter(models.Anomaly.severity == severity.strip())

    anomalies = query.order_by(models.Anomaly.start_ts.desc()).all()

    results = []
    for a in anomalies:
        results.append(schemas.AnomalyOut(
            id=a.id,
            building_id=a.building_id,
            building_name=a.building.name,
            rule=a.rule,
            start_ts=a.start_ts,
            end_ts=a.end_ts,
            wasted_kwh=round(a.wasted_kwh, 2),
            severity=a.severity,
            evidence=a.evidence,
            created_at=a.created_at,
            status=a.status
        ))

    return results

@router.patch("/{anomaly_id}", response_model=schemas.AnomalyOut)
def update_anomaly_status(
    anomaly_id: int,
    patch: schemas.AnomalyResolve,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user)
):
    anomaly = db.query(models.Anomaly).filter(models.Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    anomaly.status = patch.status.lower()
    db.commit()
    db.refresh(anomaly)

    return schemas.AnomalyOut(
        id=anomaly.id,
        building_id=anomaly.building_id,
        building_name=anomaly.building.name,
        rule=anomaly.rule,
        start_ts=anomaly.start_ts,
        end_ts=anomaly.end_ts,
        wasted_kwh=round(anomaly.wasted_kwh, 2),
        severity=anomaly.severity,
        evidence=anomaly.evidence,
        created_at=anomaly.created_at,
        status=anomaly.status
    )
