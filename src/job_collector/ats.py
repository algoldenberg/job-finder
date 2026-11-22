"""Public job board APIs: Greenhouse, Lever and SmartRecruiters."""

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime

from job_collector.httpclient import HttpClient
from job_collector.models import Job

log = logging.getLogger(__name__)

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
LEVER_URL = "https://api.lever.co/v0/postings/{slug}"
SMARTRECRUITERS_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
SMARTRECRUITERS_PAGE = 100


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json(client: HttpClient, url: str, params: dict | None = None):
    response = client.get(url, params=params)
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        log.warning("invalid JSON from %s", url)
        return None


def greenhouse(client: HttpClient, company: str, slug: str) -> list[Job]:
    data = _json(client, GREENHOUSE_URL.format(slug=slug))
    if not data:
        return []
    return [
        Job(
            source="Greenhouse",
            job_id=str(item["id"]),
            title=item["title"].strip(),
            company=company,
            location=item["location"]["name"],
            url=item["absolute_url"],
            posted=_parse_ts(item.get("first_published") or item.get("updated_at")),
        )
        for item in data.get("jobs", [])
    ]


def lever(client: HttpClient, company: str, slug: str) -> list[Job]:
    data = _json(client, LEVER_URL.format(slug=slug), params={"mode": "json"})
    if not data:
        return []
    jobs = []
    for item in data:
        categories = item.get("categories", {})
        location = ", ".join(categories.get("allLocations") or [categories.get("location", "")])
        if item.get("country") == "IL":
            location = f"{location}, Israel"
        jobs.append(
            Job(
                source="Lever",
                job_id=item["id"],
                title=item["text"].strip(),
                company=company,
                location=location,
                url=item["hostedUrl"],
                posted=datetime.fromtimestamp(item["createdAt"] / 1000, UTC),
                description=item.get("descriptionPlain", ""),
            )
        )
    return jobs


def smartrecruiters(client: HttpClient, company: str, slug: str) -> list[Job]:
    jobs: list[Job] = []
    offset = 0
    while True:
        params = {"limit": SMARTRECRUITERS_PAGE, "offset": offset}
        data = _json(client, SMARTRECRUITERS_URL.format(slug=slug), params=params)
        if not data:
            break
        for item in data.get("content", []):
            place = item.get("location", {})
            parts = [place.get("city", "")]
            if place.get("country") == "il":
                parts.append("Israel")
            jobs.append(
                Job(
                    source="SmartRecruiters",
                    job_id=item["id"],
                    title=item["name"].strip(),
                    company=company,
                    location=", ".join(p for p in parts if p),
                    url=f"https://jobs.smartrecruiters.com/{slug}/{item['id']}",
                    posted=_parse_ts(item.get("releasedDate")),
                )
            )
        offset += SMARTRECRUITERS_PAGE
        if offset >= data.get("totalFound", 0):
            break
    return jobs


FETCHERS: dict[str, Callable[[HttpClient, str, str], list[Job]]] = {
    "greenhouse": greenhouse,
    "lever": lever,
    "smartrecruiters": smartrecruiters,
}


def israel_matcher(pattern: str) -> re.Pattern:
    """Compile the location pattern, ignoring spaces around '|' left by YAML line folding."""
    return re.compile(re.sub(r"\s*\|\s*", "|", pattern.strip()), re.IGNORECASE)


def collect(
    client: HttpClient, ats_config: dict, israel_pattern: str, since: datetime
) -> list[Job]:
    """Fetch every configured company and keep jobs in Israel posted since `since`."""
    is_israel = israel_matcher(israel_pattern)
    result = []
    for platform, companies in ats_config.items():
        fetch = FETCHERS.get(platform)
        if fetch is None:
            log.warning("unknown platform in config: %s", platform)
            continue
        for company, slug in companies.items():
            found = fetch(client, company, slug)
            fresh = [
                job
                for job in found
                if job.posted and job.posted >= since and is_israel.search(job.location)
            ]
            log.info("%s %s: %d total, %d new in Israel", platform, company, len(found), len(fresh))
            result.extend(fresh)
    return result
