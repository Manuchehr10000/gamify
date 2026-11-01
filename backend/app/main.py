from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config, photos
from app.routers import admin, admin_tasks, badge, desk, feed, market, moderation, profile, quiz, rating, staff, stand

app = FastAPI(title="Event Gamification")
# The app and the API are separate Railway services; only the app's origin may call the API
app.add_middleware(CORSMiddleware, allow_origins=[config.FRONTEND_URL], allow_methods=["*"],
                   allow_headers=["Authorization", "Content-Type"])
for r in (badge.router, staff.router, admin.router, desk.router, feed.router, admin_tasks.router,
          market.router, stand.router, moderation.router, rating.router, quiz.router,
          profile.router):
    app.include_router(r)



@app.middleware("http")
async def limit_photo_size(request: Request, call_next):
    # The form parser writes the whole upload to disk before the endpoint runs: refuse big bodies up front
    if request.method == "POST" and request.url.path.endswith("/photo"):
        length = request.headers.get("content-length")
        if length is None or not length.isdigit():
            return JSONResponse({"detail": "length_required"}, status_code=411)
        if int(length) > photos.MAX_BODY:
            return JSONResponse({"detail": "photo_too_large"}, status_code=413)
    return await call_next(request)
