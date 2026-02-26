from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from bot_management_dashboard.config import get_settings
from bot_management_dashboard.database import get_db
from bot_management_dashboard.models import User
from bot_management_dashboard.security import decode_access_token, normalize_wallet_address


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/verify")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    try:
        wallet_address = normalize_wallet_address(decode_access_token(token, settings))
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc

    user = db.scalar(select(User).where(User.wallet_address == wallet_address))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User does not exist.",
        )
    return user

