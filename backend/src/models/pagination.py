"""Generic paginated response wrapper.

Usage in endpoints::

    @router.get("", response_model=PaginatedResponse[VideoResponse])
    async def list_videos(...) -> PaginatedResponse[VideoResponse]:
        ...
        return PaginatedResponse(
            items=items, total=total, limit=limit, offset=offset,
        )
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class PaginatedResponse[T](BaseModel):
    """Standard paginated response envelope."""

    items: list[T]
    total: int = Field(description="Total matching records (before LIMIT/OFFSET)")
    limit: int = Field(description="Requested page size")
    offset: int = Field(description="Requested offset")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total
