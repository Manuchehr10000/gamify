from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import accounts, config, photos, settings
from app.db import SessionLocal
from app.routers import (admin, admin_settings, admin_tasks, badge, desk, feed, jobs, live, market, moderation, profile,
                         public, quiz, rating, staff, stand)



@asynccontextmanager
async def lifespan(_app: FastAPI):
    # After `alembic upgrade head` (deploy/Dockerfile): an empty staff table takes the environment's PINs once
    with SessionLocal() as db:
        accounts.seed_if_empty(db)
        settings.ensure(db)
    yield


app = FastAPI(title="Event Gamification", lifespan=lifespan)
# The app and the API are separate Railway services; only the app's origin may call the API
app.add_middleware(CORSMiddleware, allow_origins=[config.FRONTEND_URL], allow_methods=["*"],
                   allow_headers=["Authorization", "Content-Type"])
for r in (badge.router, staff.router, admin.router, desk.router, feed.router, admin_tasks.router,
          market.router, stand.router, moderation.router, rating.router, quiz.router,
          profile.router, live.router, jobs.router, admin_settings.router, public.router):
    app.include_router(r)



# Uploads whose size is checked before the body is read: (path ending, largest body, refusal)
UPLOADS = (("/photo", photos.MAX_BODY, "photo_too_large"),
           ("/logo", admin_settings.LOGO_MAX + 64 * 1024, "logo_too_large"))


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    # The form parser writes the whole upload to disk before the endpoint runs: refuse big bodies up front
    for ending, limit, refusal in UPLOADS:
        if request.method == "POST" and request.url.path.endswith(ending):
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                return JSONResponse({"detail": "length_required"}, status_code=411)
            if int(length) > limit:
                return JSONResponse({"detail": refusal}, status_code=413)
    return await call_next(request)
