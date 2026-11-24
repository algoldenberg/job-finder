"""LinkedIn guest job search: parse result cards and fetch job descriptions."""

import html
import logging
import re
from datetime import UTC, datetime

from job_collector.httpclient import HttpClient
from job_collector.models import Job

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
VIEW_URL = "https://www.linkedin.com/jobs/view/{job_id}"
STOP_AFTER_STALE_PAGES = 2  # LinkedIn repeats results, but a later page can still bring new ones


def _clean(fragment: str) -> str:
    """Strip tags, decode entities and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    return _clean(match.group(1)) if match else ""


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_cards(page_html: str) -> list[Job]:
    """Turn one page of search results into Job objects."""
    jobs = []
    for card in page_html.split("<li>")[1:]:
        job_id = _first(r"jobPosting:(\d+)", card)
        if not job_id:
            continue
        jobs.append(
            Job(
                source="LinkedIn",
                job_id=job_id,
                title=_first(r'base-search-card__title">(.*?)</h3>', card),
                company=_first(r'base-search-card__subtitle">(.*?)</h4>', card) or "(hidden)",
                location=_first(r'job-search-card__location">(.*?)</span>', card),
                url=VIEW_URL.format(job_id=job_id),
                posted=_parse_date(_first(r'<time[^>]*datetime="([^"]+)"', card)),
            )
        )
    return jobs


def parse_description(page_html: str) -> str:
    return _first(r"show-more-less-html__markup[^>]*>(.*?)</div>", page_html)


def search(client: HttpClient, settings: dict, window_seconds: int) -> list[Job]:
    """Run every keyword search for the last window_seconds and return unique jobs."""
    found: dict[str, Job] = {}
    for index, keyword in enumerate(settings["keywords"]):
        if index:
            client.pause(settings["keyword_delay_seconds"])
        stale_pages = 0
        for page in range(settings["max_pages"]):
            if page:
                client.pause(settings["delay_seconds"])
            params = {
                "keywords": keyword,
                "location": settings["location"],
                "f_TPR": f"r{window_seconds}",
                "start": page * settings["page_size"],
            }
            response = client.get(SEARCH_URL, params=params)
            cards = parse_cards(response.text) if response is not None else []
            new = [job for job in cards if job.job_id not in found]
            for job in new:
                found[job.job_id] = job
            log.info("linkedin %r page %d: %d cards, %d new", keyword, page, len(cards), len(new))
            if not cards:
                break
            stale_pages = 0 if new else stale_pages + 1
            if stale_pages >= STOP_AFTER_STALE_PAGES:
                break
    return list(found.values())


def fetch_description(client: HttpClient, job: Job) -> None:
    """Load the full posting text into job.description (left empty on failure)."""
    response = client.get(POSTING_URL.format(job_id=job.job_id))
    if response is not None:
        job.description = parse_description(response.text)
