import pytest
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
import models
from services.analytics import CAPTURE_RATES

client = TestClient(app)

def test_capture_rates_values():
    assert CAPTURE_RATES["after_hours"] == 0.80
    assert CAPTURE_RATES["weekend_waste"] == 0.70
    assert CAPTURE_RATES["daylight_lighting"] == 0.95
    assert CAPTURE_RATES["spike"] == 0.50

def test_savings_formula_math():
    # If a rule saves 500 kWh/week at tariff INR 8.0 and emission 0.82 kg/kWh:
    kwh_week = 500.0
    tariff = 8.0
    emission = 0.82

    rupees_year = kwh_week * 52.0 * tariff
    co2_t_year = (kwh_week * 52.0 * emission) / 1000.0

    assert rupees_year == 208000.0  # 500 * 52 * 8
    assert round(co2_t_year, 2) == 21.32  # (500 * 52 * 0.82) / 1000

def test_recommendation_toggle_what_if():
    # 1. Fetch recommendations
    recs_resp = client.get("/api/recommendations")
    assert recs_resp.status_code == 200
    recs = recs_resp.json()
    assert len(recs) > 0

    first_rec = recs[0]
    rec_id = first_rec["id"]
    initial_applied = first_rec["applied"]

    # 2. Toggle applied status
    toggle_resp = client.patch(
        f"/api/recommendations/{rec_id}",
        json={"applied": not initial_applied}
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["applied"] == (not initial_applied)

    # 3. Verify summary reflects what-if applied count
    sum_resp = client.get("/api/summary")
    assert sum_resp.status_code == 200
    data = sum_resp.json()
    assert "energy_score_baseline" in data
    assert "energy_score_optimized" in data
    # Optimized score should be >= baseline score
    assert data["energy_score_optimized"] >= data["energy_score_baseline"]

    # Revert toggle
    client.patch(
        f"/api/recommendations/{rec_id}",
        json={"applied": initial_applied}
    )
