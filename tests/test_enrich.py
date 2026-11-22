import pytest

from job_collector.enrich import enrich, required_years
from job_collector.models import Job


def make_job(description: str, source: str = "LinkedIn", score: int = 2) -> Job:
    job = Job(source, "1", "IT Support", "Acme", "Tel Aviv", "https://x/1", description=description)
    job.score = score
    return job


@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("At least 3 years of experience", 3),
        ("2+ years in IT support", 2),
        ("3-5 years of experience", 3),
        ("3 to 5 years", 3),
        ("ניסיון של 2 שנים לפחות", 2),
        ("3 שנות ניסיון", 3),
        ("Founded 25 years ago. 1+ year in a NOC", 1),
        ("No numbers here", None),
    ],
)
def test_required_years(text: str, years: int | None) -> None:
    assert required_years(text) == years


def test_too_many_years_lowers_score() -> None:
    job = make_job("Requirements: 5+ years as a support engineer")
    enrich(job, max_years=4)
    assert job.score == 1
    assert job.notes == ["experience 5+ y", "likely too senior"]


def test_hebrew_and_shifts() -> None:
    job = make_job("Fluent Hebrew and English. Willing to work in shifts, 24/7 environment.")
    enrich(job, max_years=4)
    assert job.score == 2
    assert job.notes == ["Hebrew required", "shift work"]


def test_hebrew_mentioned_only() -> None:
    job = make_job("English is a must, Hebrew is an advantage.")
    enrich(job, max_years=4)
    assert job.notes == ["Hebrew mentioned"]


def test_posting_written_in_hebrew() -> None:
    text = "דרושה תומכת טכנית לחברה מובילה במרכז, עבודה במשמרות, ניסיון בתמיכה במחשבים " * 2
    job = make_job(text)
    enrich(job, max_years=4)
    assert "posting in Hebrew" in job.notes
    assert "shift work" in job.notes


def test_missing_description() -> None:
    linkedin = make_job("")
    enrich(linkedin, max_years=4)
    assert linkedin.notes == ["description not loaded"]
    greenhouse = make_job("", source="Greenhouse")
    enrich(greenhouse, max_years=4)
    assert greenhouse.notes == []
