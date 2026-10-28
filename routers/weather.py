from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from services.weather import fetch_and_cache_weather, get_cached_weather, calculate_weather_correlation

router = APIRouter(prefix="/api/weather", tags=["Weather"])

@router.get("", response_model=schemas.WeatherResponse)
def get_weather(
    days: int = Query(7, ge=1, le=30),
    building: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    # Try fetching fresh data (with timeout and fallback to cache)
    fetch_and_cache_weather(db, days=days)

    records = get_cached_weather(db, days=days)
    
    # Target building for correlation
    b_id = None
    if building and building.strip() and building.strip().lower() != "campus total":
        b = db.query(models.Building).filter(models.Building.name.ilike(building.strip())).first()
        if b:
            b_id = b.id

    corr_pct, corr_msg, days_span = calculate_weather_correlation(db, building_id=b_id)

    current_temp = records[-1].temp_c if records else 26.5

    series_pts = [schemas.WeatherPoint(ts=r.ts, temp_c=round(r.temp_c, 1)) for r in records]

    return schemas.WeatherResponse(
        current_temp_c=round(current_temp, 1),
        weather_correlation_pct=corr_pct,
        correlation_message=corr_msg,
        days_data=days_span,
        series=series_pts
    )
