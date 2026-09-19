"""Shared schema helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard envelope for list endpoints."""

    items: list[T]
    total: int = Field(description="Total number of matching rows")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class Message(BaseModel):
    detail: str
