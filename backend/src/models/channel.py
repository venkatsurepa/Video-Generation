from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChannelStatus = Literal["active", "paused", "suspended", "archived"]


class ChannelBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    youtube_channel_id: str = Field(default="", max_length=100)
    handle: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)


class ChannelCreate(ChannelBase):
    pass


class ChannelResponse(ChannelBase):
    id: uuid.UUID
    status: ChannelStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ChannelResponse:
        return cls.model_validate(row)
