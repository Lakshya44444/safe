"""Typed shapes shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Grade = Literal["A", "B", "C"]


class BinAssessment(BaseModel):
    """What the LLM must return. Validated by the gateway; invalid output triggers one repair call."""

    readable: bool = True
    contamination_pct: int = Field(ge=0, le=100)
    wrong_items: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("contamination_pct", mode="before")
    @classmethod
    def _coerce_pct(cls, v):
        if isinstance(v, str):
            v = v.strip().rstrip("%")
        v = round(float(v))
        return max(0, min(100, v))

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_conf(cls, v):
        v = float(v)
        return v / 100 if v > 1 else v

    @field_validator("wrong_items", mode="before")
    @classmethod
    def _clean_items(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        seen, out = set(), []
        for item in v:
            s = " ".join(str(item).split()).strip().lower()[:40]
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out[:6]


@dataclass
class GradeResult:
    grade: Grade
    contamination: int
    found_items: list[str] = field(default_factory=list)
    tag: str = ""
    confidence: float = 0.5
    provider: str = "mock"
    model: str = ""
    latency_ms: int = 0
    source: Literal["photo", "note"] = "photo"

    def to_dict(self) -> dict:
        return dict(self.__dict__)
