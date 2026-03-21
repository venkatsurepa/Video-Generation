from __future__ import annotations

from fastapi import APIRouter

from src.api.channels import router as channels_router
from src.api.health import router as health_router
from src.api.pipeline import router as pipeline_router
from src.api.videos import router as videos_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(videos_router, prefix="/api/v1/videos", tags=["videos"])
api_router.include_router(channels_router, prefix="/api/v1/channels", tags=["channels"])
api_router.include_router(pipeline_router, prefix="/api/v1/pipeline", tags=["pipeline"])
