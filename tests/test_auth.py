import pytest
from fastapi.testclient import TestClient
from main import app
from config import settings

client = TestClient(app)

def test_admin_login_success():
    response = client.post(
        "/api/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == settings.ADMIN_EMAIL
    assert data["user"]["role"] == "admin"

def test_viewer_login_success():
    response = client.post(
        "/api/auth/login",
        json={"email": settings.VIEWER_EMAIL, "password": settings.VIEWER_PASSWORD}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["role"] == "viewer"

def test_login_invalid_password():
    response = client.post(
        "/api/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": "WrongPassword123!"}
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

def test_auth_me_authenticated():
    # Login to get token
    login_resp = client.post(
        "/api/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD}
    )
    token = login_resp.json()["access_token"]
    
    # Query /me
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == settings.ADMIN_EMAIL

def test_auth_me_unauthenticated():
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 401
