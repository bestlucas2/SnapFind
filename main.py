"""SnapFind — FastAPI application entrypoint.

Run:  uvicorn main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import routes
from auth import AuthRedirect
from config import BASE_DIR, settings
from database import init_db
from services import processing
from templating import is_htmx

logging.basicConfig(level=logging.INFO if not settings.debug else logging.INFO)
log = logging.getLogger("snapfind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    requeued = processing.requeue_stuck()
    if requeued:
        log.info("Re-enqueued %s OCR job(s) left in 'processing'", requeued)
    purged = processing.purge_old_trash()
    if purged:
        log.info("Purged %s screenshot(s) from Trash (>30 days)", purged)
    log.info("%s ready.", settings.app_name)
    yield
    processing.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=False,
)

# Only the design assets are publicly mounted. User uploads are served through
# ownership-checked endpoints (see routes/screenshots.py), never statically.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.exception_handler(AuthRedirect)
async def auth_redirect_handler(request: Request, exc: AuthRedirect):
    if is_htmx(request):
        response = Response(status_code=204)
        response.headers["HX-Redirect"] = "/login"
        return response
    return RedirectResponse("/login", status_code=303)


app.include_router(routes.pages.router)
app.include_router(routes.auth.router)
app.include_router(routes.upload.router)
app.include_router(routes.screenshots.router)
app.include_router(routes.search.router)
app.include_router(routes.collections.router)
app.include_router(routes.tags.router)
app.include_router(routes.export.router)
app.include_router(routes.bulk.router)
app.include_router(routes.saved.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name}
