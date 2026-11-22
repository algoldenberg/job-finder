"""Hints from the job description: years of experience, Hebrew and shift work."""

import re

from job_collector.models import Job

FLAGS = re.IGNORECASE
# "3 years", "3+ years", "3-5 years", "3 to 5 years", "3 שנות ניסיון", "3 שנים"
YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?|שנות|שנים)", FLAGS
)
MAX_PLAUSIBLE_YEARS = 15  # larger numbers are usually company age, not a requirement
HEBREW_REQUIRED = re.compile(
    r"(fluent|native|excellent|high[- ]level|mother tongue|strong)[^.]{0,40}hebrew"
    r"|hebrew[^.]{0,30}(must|required|mandatory|fluent|native|is a must)"
    r"|עברית ברמה|עברית ברמת שפת אם|שליטה מלאה בעברית",
    FLAGS,
)
HEBREW_MENTIONED = re.compile(r"hebrew|עברית", FLAGS)
SHIFTS = re.compile(r"\bshifts?\b|24/7|משמרות", FLAGS)
HEBREW_LETTERS = re.compile(r"[\u0590-\u05ff]")
LATIN_LETTERS = re.compile(r"[A-Za-z]")


def required_years(text: str) -> int | None:
    """Smallest plausible number of years mentioned, or None."""
    numbers = [int(n) for n in YEARS.findall(text) if 0 < int(n) <= MAX_PLAUSIBLE_YEARS]
    return min(numbers) if numbers else None


def is_mostly_hebrew(text: str) -> bool:
    hebrew = len(HEBREW_LETTERS.findall(text))
    return hebrew > 50 and hebrew > len(LATIN_LETTERS.findall(text))


def enrich(job: Job, max_years: int) -> None:
    """Add notes from the description and lower the score of roles that ask for too much."""
    text = job.description
    if not text:
        if job.source == "LinkedIn":
            job.notes.append("description not loaded")
        return
    years = required_years(text)
    if years is not None:
        job.notes.append(f"experience {years}+ y")
        if years > max_years:
            job.score = 1
            job.notes.append("likely too senior")
    if is_mostly_hebrew(text):
        job.notes.append("posting in Hebrew")
    elif HEBREW_REQUIRED.search(text):
        job.notes.append("Hebrew required")
    elif HEBREW_MENTIONED.search(text):
        job.notes.append("Hebrew mentioned")
    if SHIFTS.search(text):
        job.notes.append("shift work")
