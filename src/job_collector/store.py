"""SQLite state: jobs already delivered and the history of runs."""

import csv
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self

from job_collector.dedupe import job_key
from job_collector.models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    url         TEXT PRIMARY KEY,
    job_key     TEXT,
    source      TEXT NOT NULL,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    first_seen  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_jobs_key ON seen_jobs (job_key);
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,
    since         TEXT NOT NULL,
    found         INTEGER NOT NULL DEFAULT 0,
    delivered     INTEGER NOT NULL DEFAULT 0,
    requests      INTEGER NOT NULL DEFAULT 0,
    rate_limited  INTEGER NOT NULL DEFAULT 0,
    failures      INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);
"""
WINDOW_OVERLAP = timedelta(hours=1)  # re-check the last hour; duplicates are filtered anyway
MAX_WINDOW = timedelta(days=7)


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.conn.close()

    # --- runs -------------------------------------------------------------------------------

    def last_success(self) -> datetime | None:
        row = self.conn.execute(
            "SELECT started_at FROM runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def window_start(self, now: datetime, default: timedelta) -> datetime:
        """Start of the search window: last successful run minus an overlap, capped at 7 days."""
        last = self.last_success()
        start = last - WINDOW_OVERLAP if last else now - default
        return max(start, now - MAX_WINDOW)

    def start_run(self, started: datetime, since: datetime) -> int:
        cursor = self.conn.execute(
            "INSERT INTO runs (started_at, status, since) VALUES (?, 'running', ?)",
            (started.isoformat(), since.isoformat()),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, status: str, **counts: int | str | None) -> None:
        allowed = {"found", "delivered", "requests", "rate_limited", "failures", "error"}
        fields = {k: v for k, v in counts.items() if k in allowed}
        assignments = ", ".join(f"{k} = ?" for k in fields)
        sql = "UPDATE runs SET status = ?, finished_at = ?" + (f", {assignments}" if fields else "")
        now = datetime.now(UTC).isoformat()
        self.conn.execute(sql + " WHERE id = ?", (status, now, *fields.values(), run_id))
        self.conn.commit()

    # --- seen jobs --------------------------------------------------------------------------

    def is_seen(self, job: Job) -> bool:
        key = job_key(job)
        row = self.conn.execute(
            "SELECT 1 FROM seen_jobs WHERE url = ? OR (job_key IS NOT NULL AND job_key = ?)",
            (job.url, key),
        ).fetchone()
        return row is not None

    def filter_new(self, jobs: list[Job]) -> list[Job]:
        return [job for job in jobs if not self.is_seen(job)]

    def remember(self, jobs: list[Job], when: datetime) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO seen_jobs (url, job_key, source, company, title, first_seen)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(j.url, job_key(j), j.source, j.company, j.title, when.isoformat()) for j in jobs],
        )
        self.conn.commit()

    def seed_from_csv(self, path: Path, when: datetime) -> int:
        """Load jobs from an earlier CSV export and record it as a successful run."""
        with path.open(encoding="utf-8", newline="") as f:
            jobs = [
                Job(
                    row["Source"],
                    row["Link"],
                    row["Role"],
                    row["Company"],
                    row["City"],
                    row["Link"],
                )
                for row in csv.DictReader(f)
            ]
        self.remember(jobs, when)
        run_id = self.start_run(when, when)
        self.finish_run(run_id, "ok", found=len(jobs), delivered=len(jobs))
        return len(jobs)
