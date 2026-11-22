"""Remove duplicates inside one run: same URL, or same company and title."""

import re

from job_collector.models import Job

COMPANY_NOISE = re.compile(
    r"\b(ltd|inc|llc|co|corp|the|software|technologies|technology|networks|group|israel)\b"
)
REQUISITION = re.compile(r"\b\d{5,}\b")  # agency ids like "198801" or "- 245443"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9א-ת]+", " ", text.lower()).strip()


def company_key(company: str) -> str:
    return re.sub(r"\s+", " ", COMPANY_NOISE.sub(" ", _normalize(company))).strip()


def title_key(title: str) -> str:
    return _normalize(REQUISITION.sub(" ", title))


def job_key(job: Job) -> str | None:
    """Company and title key, or None when the company is hidden and cannot be compared."""
    if job.company == "(hidden)":
        return None
    return f"{company_key(job.company)}|{title_key(job.title)}"


def dedupe(jobs: list[Job]) -> list[Job]:
    """Keep the first copy of each job. Company sites win over LinkedIn."""
    ordered = sorted(jobs, key=lambda job: job.source == "LinkedIn")  # stable sort
    seen_urls: set[str] = set()
    by_key: dict[str, Job] = {}
    result = []
    for job in ordered:
        if job.url in seen_urls:
            continue
        key = job_key(job)
        if key is not None and key in by_key:
            first = by_key[key]
            if job.source != first.source and job.source not in first.also_in:
                first.also_in.append(job.source)
            continue
        seen_urls.add(job.url)
        if key is not None:
            by_key[key] = job
        result.append(job)
    return result
