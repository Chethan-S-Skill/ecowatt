import io
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_csv_upload_valid():
    csv_content = """timestamp,building,kwh
2026-10-25 10:00:00,Computer Labs,145.5
2026-10-25 11:00:00,Computer Labs,152.0
2026-10-25 12:00:00,Computer Labs,158.2
"""
    files = {"file": ("valid_meter.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/upload-csv", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["rows_loaded"] == 3
    assert data["rows_skipped"] == 0

def test_csv_upload_bad_rows_skipped():
    csv_content = """timestamp,building,kwh
2026-10-25 10:00:00,Computer Labs,140.0
invalid-date-format,Computer Labs,135.0
2026-10-25 12:00:00,Computer Labs,-25.0
2026-10-25 13:00:00,Unknown Moon Base,100.0
2026-10-25 10:00:00,Computer Labs,140.0
"""
    files = {"file": ("mixed.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/upload-csv", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total_rows"] == 5
    assert data["rows_loaded"] == 1
    assert data["rows_skipped"] == 4
    assert len(data["skipped_reasons"]) > 0

def test_csv_missing_headers():
    csv_content = """date,site,power
2026-10-25 10:00:00,Computer Labs,140.0
"""
    files = {"file": ("missing_headers.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post("/api/upload-csv", files=files)
    assert response.status_code == 400
    assert "CSV must contain" in response.json()["detail"]
