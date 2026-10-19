"""Signed bearer tokens. The demo account is created in seed and documented in the README."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.entities import User

bearer = HTTPBearer(auto_error=False)


def secret() -> bytes:
    return os.environ.get("VALUATIONLAB_SECRET", "dev-only-change-me").encode()


def hash_password(password: str, salt: str | None = None) -> str:
    chosen = salt or hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), chosen.encode(), 200_000)
    return f"{chosen}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, _, digest = stored.partition("$")
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored if digest else "")


def issue_token(user: User) -> str:
    payload = {"sub": user.id, "username": user.username, "exp": int(time.time()) + 60 * 60 * 12}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_token(token: str) -> dict:
    body, _, signature = token.partition(".")
    expected = hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid token")
    padded = body + "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if int(payload.get("exp", 0)) < time.time():
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


@dataclass
class CurrentUser:
    id: str
    username: str


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = read_token(credentials.credentials)
    user = db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return CurrentUser(id=user.id, username=user.username)


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Unknown username or password")
    return user
