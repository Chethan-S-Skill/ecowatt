import pytest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from database import SessionLocal
import models
from services.analytics import calculate_energy_score, run_analytics_for_buildings

def test_energy_score_formula():
    # 0 wasted -> score 100
    assert calculate_energy_score(10000.0, 0.0) == 100.0

    # 10% wasted -> 100 - (0.10 * 400) = 60.0
    assert calculate_energy_score(1000.0, 100.0) == 60.0

    # 30% wasted -> 100 - (0.30 * 400) = -20 clamped to 0.0
    assert calculate_energy_score(1000.0, 300.0) == 0.0

    # Empty total -> default 100.0
    assert calculate_energy_score(0.0, 0.0) == 100.0

def test_seeded_anomalies_and_rules():
    db = SessionLocal()
    try:
        # Check that computer labs has after-hours anomalies
        labs = db.query(models.Building).filter(models.Building.name == "Computer Labs").first()
        assert labs is not None
        lab_anoms = db.query(models.Anomaly).filter(
            models.Anomaly.building_id == labs.id,
            models.Anomaly.rule == "after_hours"
        ).all()
        assert len(lab_anoms) > 0
        assert all(a.wasted_kwh > 0 for a in lab_anoms)

        # Check that Academic Block has weekend_waste anomalies
        acad = db.query(models.Building).filter(models.Building.name == "Academic Block").first()
        assert acad is not None
        acad_anoms = db.query(models.Anomaly).filter(
            models.Anomaly.building_id == acad.id,
            models.Anomaly.rule == "weekend_waste"
        ).all()
        assert len(acad_anoms) > 0

        # Check that Outdoor Lighting has daylight_lighting anomalies
        light = db.query(models.Building).filter(models.Building.name == "Outdoor Lighting").first()
        assert light is not None
        light_anoms = db.query(models.Anomaly).filter(
            models.Anomaly.building_id == light.id,
            models.Anomaly.rule == "daylight_lighting"
        ).all()
        assert len(light_anoms) > 0

        # Check that 24h buildings (Hostel, Cafeteria) do NOT have after_hours anomalies
        hostel = db.query(models.Building).filter(models.Building.name == "Hostel Block").first()
        assert hostel.is_24h is True
        hostel_ah = db.query(models.Anomaly).filter(
            models.Anomaly.building_id == hostel.id,
            models.Anomaly.rule == "after_hours"
        ).count()
        assert hostel_ah == 0
    finally:
        db.close()
