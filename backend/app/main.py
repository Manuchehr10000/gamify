from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.routers import admin, admin_tasks, badge, desk, feed, staff

app = FastAPI(title="Event Gamification")
# The app and the API are separate Railway services; only the app's origin may call the API
app.add_middleware(CORSMiddleware, allow_origins=[config.FRONTEND_URL], allow_methods=["*"],
                   allow_headers=["Authorization", "Content-Type"])
for r in (badge.router, staff.router, admin.router, desk.router, feed.router, admin_tasks.router):
    app.include_router(r)
