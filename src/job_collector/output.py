"""CSV output. The same columns will be used for Google Sheets."""

import csv
import re
from datetime import datetime
from pathlib import Path

from job_collector.models import Job

COLUMNS = [
    "Added",
    "Posted",
    "Company",
    "Role",
    "City",
    "Link",
    "Source",
    "CV",
    "Score",
    "Also in",
    "Notes",
    "Status",
    "Sent on",
    "Comments",
]


def short_city(location: str) -> str:
    """'Tel Aviv-Yafo, Tel Aviv District, Israel' -> 'Tel Aviv-Yafo, Tel Aviv'."""
    city = re.sub(r"\s*District\b", "", location)
    city = re.sub(r",?\s*(Israel|il)\s*$", "", city, flags=re.IGNORECASE)
    return city.strip(" ,")


def to_row(job: Job, added: datetime) -> list[str]:
    return [
        added.strftime("%Y-%m-%d"),
        job.posted.strftime("%Y-%m-%d") if job.posted else "",
        job.company,
        job.title,
        short_city(job.location),
        job.url,
        job.source,
        job.cv,
        str(job.score),
        ", ".join(job.also_in),
        "; ".join(job.notes),
        "",
        "",
        "",
    ]


def sort_jobs(jobs: list[Job]) -> list[Job]:
    return sorted(jobs, key=lambda j: (-j.score, j.cv, j.company.lower(), j.title.lower()))


def write_csv(jobs: list[Job], path: Path, added: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(to_row(job, added) for job in sort_jobs(jobs))
