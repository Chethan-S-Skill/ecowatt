import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List
import httpx
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func
import models

logger = logging.getLogger("ecowatt.weather")

# Open-Meteo endpoint (Bengaluru/India campus lat=12.9716, lon=77.5946)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def fetch_and_cache_weather(db: Session, days: int = 28) -> int:
    """
    Fetches hourly temperature from Open-Meteo and caches in the weather table.
    Uses a 3-second timeout and gracefully catches network errors to support offline demo mode.
    Returns number of newly cached records.
    """
    params = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "hourly": "temperature_2m",
        "past_days": min(days, 28),
        "forecast_days": 2,
        "timezone": "auto"
    }
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(OPEN_METEO_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                
                cached_count = 0
                for t_str, temp in zip(times, temps):
                    if temp is None:
                        continue
                    dt = datetime.fromisoformat(t_str)
                    existing = db.query(models.Weather).filter(models.Weather.ts == dt).first()
                    if not existing:
                        db.add(models.Weather(ts=dt, temp_c=float(temp)))
                        cached_count += 1
                db.commit()
                logger.info(f"Open-Meteo weather synced: {cached_count} new records cached.")
                return cached_count
    except Exception as e:
        logger.warning(f"Open-Meteo fetch failed ({e}). Using existing cached weather data.")
        db.rollback()
    return 0

def get_cached_weather(db: Session, days: int = 7) -> List[models.Weather]:
    """Retrieves cached weather records up to the specified days back."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return db.query(models.Weather).filter(models.Weather.ts >= cutoff).order_by(models.Weather.ts.asc()).all()

def calculate_weather_correlation(db: Session, building_id: Optional[int] = None) -> Tuple[Optional[float], str, int]:
    """
    Correlates temperature with load for a building or campus.
    Returns: (correlation_pct, message, days_of_data)
    Strict rule: Only returns correlation % when there are at least 14 days of weather data!
    """
    # Check weather data span
    min_weather_ts = db.query(func.min(models.Weather.ts)).scalar()
    max_weather_ts = db.query(func.max(models.Weather.ts)).scalar()
    
    if not min_weather_ts or not max_weather_ts:
        return None, "No weather data cached yet. Requires 14 days of history.", 0
        
    days_span = (max_weather_ts - min_weather_ts).days
    if days_span < 14:
        return None, f"Insufficient weather history ({days_span} days). At least 14 days required.", days_span

    # Join meter_readings with weather on matching hourly timestamp
    query = db.query(models.MeterReading.kwh, models.Weather.temp_c)\
        .join(models.Weather, models.MeterReading.ts == models.Weather.ts)
        
    if building_id:
        query = query.filter(models.MeterReading.building_id == building_id)
        
    results = query.all()
    if len(results) < 14 * 24:
        return None, f"Not enough synchronized reading/weather pairs ({len(results)} samples).", days_span

    loads = np.array([r[0] for r in results], dtype=float)
    temps = np.array([r[1] for r in results], dtype=float)

    # Check for variance
    if np.std(loads) < 1e-4 or np.std(temps) < 1e-4:
        return 0.0, "Load or temperature exhibits near-zero variance.", days_span

    # Pearson correlation r, R^2 = r^2
    corr_matrix = np.corrcoef(loads, temps)
    r = corr_matrix[0, 1]
    r_squared_pct = round(float((r ** 2) * 100), 1)

    building_label = "this building" if building_id else "the campus"
    msg = f"{r_squared_pct}% of {building_label}'s energy variation is weather-related (R² = {r**2:.2f}, r = {r:.2f})"
    return r_squared_pct, msg, days_span
