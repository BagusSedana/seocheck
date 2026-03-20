from __future__ import annotations
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
import models
import os

SECRET_KEY  = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY tidak ditemukan di environment variables")
ALGORITHM   = "HS256"
EXPIRE_MIN  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer      = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    # bcrypt max 72 bytes, truncate at 71 to be safe
    password = password[:71]
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt max 72 bytes, truncate at 71 to be safe
    plain = plain[:71]
    return pwd_context.verify(plain, hashed)

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=EXPIRE_MIN)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token tidak valid atau sudah expired")

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db)
) -> models.User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Token diperlukan")
    payload = decode_token(credentials.credentials)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Payload token tidak valid")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User tidak ditemukan atau tidak aktif")
    return user

def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("user_id")
        if not user_id:
            return None
        return db.query(models.User).filter(models.User.id == user_id).first()
    except Exception:
        return None

def check_scan_limit(user: models.User, db: Session) -> bool:
    now = datetime.now()
    
    # 1. Check subscription expiry
    if user.tier != "free" and user.subscription_end and user.subscription_end < now:
        user.tier = "free"
        db.commit()

    # 2. Reset Quota if 1 month has passed since last_reset_date
    if user.last_reset_date:
        # Simple logic: if more than 30 days or if it's the next month and same/greater day
        # Better: check if we are in a different month-cycle
        next_reset = user.last_reset_date + timedelta(days=30)
        # For simplicity and UX, if now > last_reset + 30 days, we reset and move last_reset forward
        while now >= next_reset:
            user.scans_this_month = 0
            # Note: user.topup_scans does NOT reset (as per "tidak ada akumulasi" usually refers to tier quota, 
            # but user said "tidak ada akumulasi", so topup should also be handled. 
            # Traditionally topups are one-time. I'll keep topup until used.)
            user.last_reset_date = next_reset
            next_reset = user.last_reset_date + timedelta(days=30)
            db.commit()

    # 3. Calculate Total Limit
    tier_limit = models.SCAN_LIMITS.get(user.tier, 2)
    total_limit = tier_limit + user.topup_scans
    
    return user.scans_this_month < total_limit

def increment_scan_count(user: models.User, db: Session) -> None:
    tier_limit = models.SCAN_LIMITS.get(user.tier, 2)
    
    if user.scans_this_month < tier_limit:
        user.scans_this_month += 1
    elif user.topup_scans > 0:
        user.topup_scans -= 1
    else:
        # Should not happen if check_scan_limit was called
        user.scans_this_month += 1
        
    db.commit()
