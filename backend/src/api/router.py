from __future__ import annotations

from fastapi import APIRouter

from src.api.analytics import router as analytics_router
from src.api.channels import router as channels_router
from src.api.community import router as community_router
from src.api.health import router as health_router
from src.api.pipeline import router as pipeline_router
from src.api.research import router as research_router
from src.api.schedule import router as schedule_router
from src.api.series import router as series_router
from src.api.topics import router as topics_router
from src.api.videos import router as videos_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(videos_router, prefix="/api/v1/videos", tags=["videos"])
api_router.include_router(channels_router, prefix="/api/v1/channels", tags=["channels"])
api_router.include_router(pipeline_router, prefix="/api/v1/pipeline", tags=["pipeline"])
api_router.include_router(topics_router, prefix="/api/v1/topics", tags=["topics"])
api_router.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
api_router.include_router(schedule_router, prefix="/api/v1/schedule", tags=["schedule"])
api_router.include_router(series_router, prefix="/api/v1/series", tags=["series"])
api_router.include_router(community_router, prefix="/api/v1/community", tags=["community"])
api_router.include_router(research_router, prefix="/api/v1/research", tags=["research"])
