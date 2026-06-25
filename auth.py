"""Authentication, session handling, CSRF, and ownership enforcement.

Every single-record access in the app funnels through `get_owned_*` so that
ownership is checked in exactly one place and no route can read another user's
data via a guessed id (IDOR).
"""
from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Collection, Screenshot, Tag, User


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    # bcrypt only considers the first 72 bytes; truncate explicitly so longer
    # inputs don't raise on some backends.
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_user(db: Session, email: str, password: str, display_name: str) -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        display_name=display_name.strip() or email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()
    if user and verify_password(password, user.password_hash):
        return user
    return None


# --------------------------------------------------------------------------- #
# Session / current user
# --------------------------------------------------------------------------- #
def login_session(request: Request, user: User) -> None:
    request.session["user_id"] = user.id
    # Rotate CSRF token on login.
    request.session["csrf_token"] = secrets.token_urlsafe(32)


def logout_session(request: Request) -> None:
    request.session.clear()


def get_optional_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.get(User, uid)


class AuthRedirect(Exception):
    """Raised when an unauthenticated user hits a protected route."""


def require_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    uid = request.session.get("user_id")
    user = db.get(User, uid) if uid else None
    if user is None:
        raise AuthRedirect()
    return user


# --------------------------------------------------------------------------- #
# CSRF
# --------------------------------------------------------------------------- #
def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


async def verify_csrf(request: Request) -> None:
    """Dependency for every state-changing request (cookie auth ⇒ CSRF risk)."""
    session_token = request.session.get("csrf_token")
    sent = request.headers.get("x-csrf-token")
    if not sent and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        content_type = request.headers.get("content-type", "")
        if "form" in content_type or "multipart" in content_type:
            form = await request.form()
            sent = form.get("csrf_token")
    if (
        not session_token
        or not sent
        or not secrets.compare_digest(str(session_token), str(sent))
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token"
        )


# --------------------------------------------------------------------------- #
# Ownership helpers  (the single chokepoint for per-user isolation)
# --------------------------------------------------------------------------- #
def get_owned_screenshot(
    screenshot_id: int, user: User, db: Session
) -> Screenshot:
    obj = db.execute(
        select(Screenshot).where(
            Screenshot.id == screenshot_id, Screenshot.user_id == user.id
        )
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return obj


def get_owned_collection(
    collection_id: int, user: User, db: Session
) -> Collection:
    obj = db.execute(
        select(Collection).where(
            Collection.id == collection_id, Collection.user_id == user.id
        )
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return obj


def get_owned_tag(tag_id: int, user: User, db: Session) -> Tag:
    obj = db.execute(
        select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id)
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return obj
