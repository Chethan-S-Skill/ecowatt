from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from auth import get_current_user

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])

@router.get("", response_model=List[schemas.RecommendationOut])
def get_recommendations(
    building: Optional[str] = Query(None, description="Filter by building name"),
    db: Session = Depends(get_db)
):
    query = db.query(models.Recommendation).join(models.Building)

    if building and building.strip() and building.strip().lower() != "campus total":
        query = query.filter(models.Building.name.ilike(building.strip()))

    recs = query.order_by(models.Recommendation.rupees_year.desc()).all()

    results = []
    for r in recs:
        results.append(schemas.RecommendationOut(
            id=r.id,
            building_id=r.building_id,
            building_name=r.building.name,
            anomaly_rule=r.anomaly_rule,
            fix_text=r.fix_text,
            capture_rate=r.capture_rate,
            kwh_week=round(r.kwh_week, 1),
            rupees_year=round(r.rupees_year, 1),
            co2_t_year=round(r.co2_t_year, 2),
            applied=r.applied
        ))

    return results

@router.patch("/{rec_id}", response_model=schemas.RecommendationOut)
def toggle_recommendation(
    rec_id: int,
    patch: schemas.RecommendationToggle,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user)
):
    rec = db.query(models.Recommendation).filter(models.Recommendation.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.applied = patch.applied
    db.commit()
    db.refresh(rec)

    return schemas.RecommendationOut(
        id=rec.id,
        building_id=rec.building_id,
        building_name=rec.building.name,
        anomaly_rule=rec.anomaly_rule,
        fix_text=rec.fix_text,
        capture_rate=rec.capture_rate,
        kwh_week=round(rec.kwh_week, 1),
        rupees_year=round(rec.rupees_year, 1),
        co2_t_year=round(rec.co2_t_year, 2),
        applied=rec.applied
    )
