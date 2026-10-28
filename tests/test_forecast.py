import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal, Base, engine
import models
from services.forecast import generate_forecast

client = TestClient(app)

def test_forecast_24h_success():
    response = client.get("/api/forecast?horizon=24h")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["points"]) == 24
    assert "predicted_kwh" in data["points"][0]
    assert "lower_bound_kwh" in data["points"][0]
    assert "upper_bound_kwh" in data["points"][0]

def test_forecast_7d_success():
    response = client.get("/api/forecast?horizon=7d&building=Computer%20Labs")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["points"]) == 168

def test_forecast_insufficient_history_returns_clear_message():
    db = SessionLocal()
    try:
        # Create a dummy temporary building with only 3 days of readings
        test_b = models.Building(
            name="Temporary Trailer",
            type="admin",
            is_24h=False,
            peak_kw=50.0,
            idle_pct=0.1
        )
        db.add(test_b)
        db.commit()
        db.refresh(test_b)

        now = datetime.utcnow()
        for i in range(48): # 2 days only
            db.add(models.MeterReading(
                building_id=test_b.id,
                ts=now - timedelta(hours=i),
                kwh=20.0
            ))
        db.commit()

        # Run forecast on this building
        res = generate_forecast(db, building_id=test_b.id, horizon="24h")
        assert res["status"] == "not_enough_history"
        assert "At least 14 days" in res["message"]
        assert len(res["points"]) == 0

        # Clean up
        db.query(models.MeterReading).filter(models.MeterReading.building_id == test_b.id).delete()
        db.delete(test_b)
        db.commit()
    finally:
        db.close()
