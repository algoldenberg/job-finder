"""Data model shared by all sources and outputs."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    source: str
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted: datetime | None = None
    description: str = ""
    cv: str = ""
    score: int = 0
    notes: list[str] = field(default_factory=list)
    also_in: list[str] = field(default_factory=list)  # other sources with the same job
