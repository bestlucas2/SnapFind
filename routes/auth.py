"""Registration, login, logout, profile, and account management."""
from __future__ import annotations

import io
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import (
    authenticate,
    create_user,
    hash_password,
    login_session,
    logout_session,
    require_user,
    verify_csrf,
    verify_password,
)
from config import settings
from database import get_db
from models import Screenshot, User
from services import export as export_service
from services.storage import get_storage
from templating import base_context, templates
from utils.files import get_bytes
from utils.ratelimit import (
    client_ip,
    login_block_seconds,
    record_login_failure,
    record_login_success,
)

router = APIRouter()


def _profile(request, user, db, *, message=None, error=None, status=200):
    ctx = base_context(request, user, db, message=message, error=error)
    return templates.TemplateResponse("auth/profile.html", ctx, status_code=status)


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse("auth/login.html", base_context(request, None))


@router.post("/login", dependencies=[Depends(verify_csrf)])
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = client_ip(request)
    email_norm = email.strip().lower()

    wait = login_block_seconds(ip, email_norm)
    if wait:
        minutes = max(1, round(wait / 60))
        ctx = base_context(
            request,
            None,
            error=f"Too many login attempts. Please try again in about {minutes} minute(s).",
            email=email,
        )
        return templates.TemplateResponse("auth/login.html", ctx, status_code=429)

    user = authenticate(db, email, password)
    if not user:
        record_login_failure(ip, email_norm)
        ctx = base_context(
            request, None, error="Invalid email or password.", email=email
        )
        return templates.TemplateResponse("auth/login.html", ctx, status_code=400)

    record_login_success(ip, email_norm)
    login_session(request, user)
    return RedirectResponse("/app", status_code=303)


@router.get("/register")
def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse("auth/register.html", base_context(request, None))


@router.post("/register", dependencies=[Depends(verify_csrf)])
def register_submit(
    request: Request,
    display_name: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    def fail(message: str) -> Response:
        ctx = base_context(
            request, None, error=message, email=email, display_name=display_name
        )
        return templates.TemplateResponse("auth/register.html", ctx, status_code=400)

    email_norm = email.strip().lower()
    if len(password) < 6:
        return fail("Password must be at least 6 characters.")
    if password != confirm:
        return fail("Passwords do not match.")
    exists = db.execute(
        select(User).where(User.email == email_norm)
    ).scalar_one_or_none()
    if exists:
        return fail("An account with that email already exists.")

    user = create_user(db, email_norm, password, display_name)
    login_session(request, user)
    return RedirectResponse("/app", status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    logout_session(request)
    return RedirectResponse("/", status_code=303)


@router.get("/profile")
def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        "auth/profile.html", base_context(request, user, db)
    )


@router.post("/profile", dependencies=[Depends(verify_csrf)])
def profile_update(
    request: Request,
    display_name: str = Form(...),
    current_password: str = Form(""),
    new_password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    message = None
    error = None
    user.display_name = display_name.strip() or user.display_name

    if new_password:
        if not verify_password(current_password, user.password_hash):
            error = "Current password is incorrect."
        elif len(new_password) < 6:
            error = "New password must be at least 6 characters."
        else:
            user.password_hash = hash_password(new_password)
            message = "Password updated."

    if error is None:
        db.commit()
        message = message or "Profile updated."
    else:
        db.rollback()

    ctx = base_context(request, user, db, message=message, error=error)
    return templates.TemplateResponse("auth/profile.html", ctx)


@router.post("/account/email", dependencies=[Depends(verify_csrf)])
def change_email(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    new = email.strip().lower()
    if "@" not in new or "." not in new:
        return _profile(request, user, db, error="Enter a valid email.", status=400)
    if new != user.email:
        exists = db.execute(
            select(User).where(User.email == new, User.id != user.id)
        ).scalar_one_or_none()
        if exists is not None:
            return _profile(request, user, db, error="That email is already in use.", status=400)
        user.email = new
        db.commit()
    return _profile(request, user, db, message="Email updated.")


@router.post("/account/avatar", dependencies=[Depends(verify_csrf)])
def upload_avatar(  # sync: PIL + Supabase Storage upload are blocking
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    file.file.seek(0)
    data = file.file.read()
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            w, h = img.size
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize((256, 256))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
        get_storage().put(f"{user.id}/avatar.jpg", buf.getvalue(), "image/jpeg")
    except Exception:
        return _profile(request, user, db, error="That image couldn't be processed.", status=400)
    user.avatar_path = f"{user.id}/avatar.jpg"
    db.commit()
    return _profile(request, user, db, message="Avatar updated.")


@router.get("/profile/avatar")
def get_avatar(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.avatar_path:
        return Response(status_code=404)
    data = get_bytes(user.avatar_path)
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type="image/jpeg")


@router.get("/account/export")
def export_account(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shots = (
        db.execute(
            select(Screenshot).where(
                Screenshot.user_id == user.id, Screenshot.deleted_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    body = export_service.to_zip(shots)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="snapfind-data-{stamp}.zip"'
        },
    )


@router.post("/account/delete", dependencies=[Depends(verify_csrf)])
def delete_account(
    request: Request,
    current_password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not verify_password(current_password, user.password_hash):
        return _profile(request, user, db, error="Password is incorrect.", status=400)
    # Remove the user's stored files, then the rows (relationships cascade).
    shutil.rmtree(settings.storage_path / str(user.id), ignore_errors=True)
    db.delete(user)
    db.commit()
    logout_session(request)
    return RedirectResponse("/", status_code=303)
