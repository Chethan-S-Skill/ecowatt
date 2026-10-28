import io
import csv
import logging
from datetime import datetime
from typing import List, Union, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Header, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import get_db
import models
import schemas
from config import settings
from auth import verify_meter_key, get_current_user
from services.analytics import run_analytics_for_buildings

logger = logging.getLogger("ecowatt.readings")
router = APIRouter(prefix="/api", tags=["Meter Readings & Ingestion"])

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_UPLOAD_ROWS = 200_000

@router.post("/readings")
def post_readings(
    payload: Union[schemas.MeterReadingBatch, schemas.MeterReadingCreate, List[schemas.MeterReadingCreate]],
    background_tasks: BackgroundTasks,
    x_meter_key: Optional[str] = Header(None, alias="X-Meter-Key"),
    current_user: Optional[models.User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ingests single or batch meter readings.
    Requires valid X-Meter-Key header or authenticated admin user.
    Automatically enqueues analytics re-run for affected buildings.
    """
    # Security check: Either valid meter key OR admin user
    is_valid_key = (x_meter_key == settings.METER_API_KEY)
    is_admin = (current_user and current_user.role == "admin")

    if not is_valid_key and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Meter-Key header (or admin login required)"
        )

    # Normalize payload into list of readings
    raw_readings: List[schemas.MeterReadingCreate] = []
    if isinstance(payload, schemas.MeterReadingBatch):
        raw_readings = payload.readings
    elif isinstance(payload, list):
        raw_readings = payload
    else:
        raw_readings = [payload]

    if not raw_readings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readings provided")

    # Map building names to IDs
    building_map = {b.name.lower(): b.id for b in db.query(models.Building).all()}
    inserted = 0
    skipped = 0
    affected_building_ids = set()

    for item in raw_readings:
        b_name = item.building.strip().lower()
        if b_name not in building_map:
            skipped += 1
            continue

        b_id = building_map[b_name]
        affected_building_ids.add(b_id)

        # Upsert or ignore duplicate (building_id, ts)
        existing = db.query(models.MeterReading).filter(
            models.MeterReading.building_id == b_id,
            models.MeterReading.ts == item.timestamp
        ).first()

        if existing:
            existing.kwh = item.kwh
        else:
            db.add(models.MeterReading(
                building_id=b_id,
                ts=item.timestamp,
                kwh=item.kwh
            ))
        inserted += 1

    db.commit()

    # Re-run analytics for affected buildings
    if affected_building_ids:
        run_analytics_for_buildings(db, list(affected_building_ids))

    return {
        "status": "success",
        "readings_received": len(raw_readings),
        "readings_loaded": inserted,
        "readings_skipped": skipped,
        "affected_buildings": len(affected_building_ids)
    }

@router.post("/upload-csv", response_model=schemas.CsvUploadSummary)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user)
):
    """
    Upload and validate CSV meter data file.
    Expected columns: timestamp, building, kwh
    Enforces 10MB limit and 200,000 row max.
    Skips bad rows, returns detailed summary, and recalculates building analytics.
    """
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size limit of 10 MB."
        )

    try:
        decoded = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = contents.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Cannot decode CSV file. Must be UTF-8 or ASCII.")

    reader = csv.reader(io.StringIO(decoded))
    try:
        header = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    # Match column indices
    norm_headers = [h.strip().lower() for h in header]
    try:
        ts_idx = norm_headers.index("timestamp")
        b_idx = norm_headers.index("building")
        kwh_idx = norm_headers.index("kwh")
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain 'timestamp', 'building', and 'kwh' columns. Found: {header}"
        )

    # Building name cache
    buildings = db.query(models.Building).all()
    building_map = {b.name.lower(): b.id for b in buildings}

    total_rows = 0
    loaded_count = 0
    skipped_count = 0
    skipped_reasons: List[str] = []
    affected_building_ids = set()
    seen_in_batch = set()

    for row_num, row in enumerate(reader, start=2):
        total_rows += 1
        if total_rows > MAX_UPLOAD_ROWS:
            skipped_reasons.append(f"Row {row_num}: Exceeded maximum allowed limit of {MAX_UPLOAD_ROWS} rows.")
            skipped_count += 1
            break

        if not row or len(row) < 3:
            skipped_count += 1
            if len(skipped_reasons) < 25:
                skipped_reasons.append(f"Row {row_num}: Incomplete row data.")
            continue

        # 1. Parse Building
        b_name_raw = row[b_idx].strip()
        b_key = b_name_raw.lower()
        if b_key not in building_map:
            skipped_count += 1
            if len(skipped_reasons) < 25:
                skipped_reasons.append(f"Row {row_num}: Unknown building '{b_name_raw}'.")
            continue
        b_id = building_map[b_key]

        # 2. Parse Timestamp
        ts_str = row[ts_idx].strip()
        parsed_ts = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                parsed_ts = datetime.strptime(ts_str, fmt)
                break
            except ValueError:
                pass

        if not parsed_ts:
            try:
                parsed_ts = datetime.fromisoformat(ts_str)
            except Exception:
                pass

        if not parsed_ts:
            skipped_count += 1
            if len(skipped_reasons) < 25:
                skipped_reasons.append(f"Row {row_num}: Invalid date format '{ts_str}'.")
            continue

        # 3. Parse kWh
        kwh_str = row[kwh_idx].strip()
        try:
            kwh_val = float(kwh_str)
            if kwh_val < 0 or not (kwh_val == kwh_val): # NaN check
                raise ValueError("Negative or NaN value")
        except ValueError:
            skipped_count += 1
            if len(skipped_reasons) < 25:
                skipped_reasons.append(f"Row {row_num}: Non-numeric or negative kWh '{kwh_str}'.")
            continue

        # 4. Check Duplicate within file or DB
        pair_key = (b_id, parsed_ts)
        if pair_key in seen_in_batch:
            skipped_count += 1
            if len(skipped_reasons) < 25:
                skipped_reasons.append(f"Row {row_num}: Duplicate record within file for {b_name_raw} at {ts_str}.")
            continue
        seen_in_batch.add(pair_key)

        # Upsert into database
        existing = db.query(models.MeterReading).filter(
            models.MeterReading.building_id == b_id,
            models.MeterReading.ts == parsed_ts
        ).first()

        if existing:
            existing.kwh = kwh_val
        else:
            db.add(models.MeterReading(
                building_id=b_id,
                ts=parsed_ts,
                kwh=kwh_val
            ))

        loaded_count += 1
        affected_building_ids.add(b_id)

    db.commit()

    # Re-run analytics for affected buildings
    if affected_building_ids:
        run_analytics_for_buildings(db, list(affected_building_ids))

    return schemas.CsvUploadSummary(
        total_rows=total_rows,
        rows_loaded=loaded_count,
        rows_skipped=skipped_count,
        skipped_reasons=skipped_reasons
    )
