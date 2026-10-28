import time
from datetime import datetime, timedelta
from typing import Dict, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from auth import verify_password, create_access_token, require_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# In-memory rate limiter for login: client_ip -> (attempts, reset_time)
login_attempts: Dict[str, Tuple[int, float]] = {}
MAX_LOGIN_ATTEMPTS = 10
LOCKOUT_SECONDS = 60

def check_login_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    attempts, reset_time = login_attempts.get(client_ip, (0, now + LOCKOUT_SECONDS))

    if now > reset_time:
        login_attempts[client_ip] = (1, now + LOCKOUT_SECONDS)
        return

    if attempts >= MAX_LOGIN_ATTEMPTS:
        remaining = int(reset_time - now)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please wait {remaining} seconds."
        )

    login_attempts[client_ip] = (attempts + 1, reset_time)

@router.post("/login", response_model=schemas.Token)
def login(login_data: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    check_login_rate_limit(request)

    user = db.query(models.User).filter(models.User.email == login_data.email.strip().lower()).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reset rate limit on success
    client_ip = request.client.host if request.client else "127.0.0.1"
    if client_ip in login_attempts:
        del login_attempts[client_ip]

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "id": user.id}
    )

    return schemas.Token(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserOut.model_validate(user)
    )

@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(require_current_user)):
    return schemas.UserOut.model_validate(current_user)
