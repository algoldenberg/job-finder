import pytest

from job_collector.classify import Classifier
from job_collector.config import load_config
from job_collector.models import Job


@pytest.fixture(scope="module")
def classifier() -> Classifier:
    return Classifier.from_config(load_config())


def make_job(title: str) -> Job:
    return Job(
        source="test",
        job_id="1",
        title=title,
        company="Acme",
        location="Tel Aviv",
        url="https://example.com/1",
    )


@pytest.mark.parametrize(
    ("title", "cv", "score"),
    [
        ("Junior Information Technology Support", "IT_Support", 3),
        ("Help Desk Engineer", "IT_Support", 2),
        ("Cloud System Engineer - Microsoft 365", "IT_Support", 2),
        ("System Administrator", "IT_Support", 2),
        ("NOC Engineer Tier 1", "NOC", 3),
        ("Network Operations Center Analyst", "NOC", 2),
        ("Technical Support Engineer", "Technical_Support", 2),
        ("Customer Support Agent (Native-Level English)", "Technical_Support", 2),
        ("DevOps Engineer", "DevOps", 1),
        ("Junior DevOps Engineer", "DevOps", 3),
        ("Platform Engineer", "DevOps", 1),
    ],
)
def test_accepted_titles(classifier: Classifier, title: str, cv: str, score: int) -> None:
    job = make_job(title)
    assert classifier.classify(job)
    assert (job.cv, job.score) == (cv, score)


@pytest.mark.parametrize(
    "title",
    [
        "Senior DevOps Engineer",
        "Sr. System Administrator",
        "IT Team Lead",
        "Travel Coordinator (Student)",
        "Backend Engineer",
        "Sales Support Specialist",
        "Data Platform Engineer (Kafka Oriented)",
        "X-ray Integration Engineer",
        "QA Engineer & Production Support",
        "Product Designer - UX/UI",
        "Information Technology Procurement",
    ],
)
def test_rejected_titles(classifier: Classifier, title: str) -> None:
    assert not classifier.classify(make_job(title))


@pytest.mark.parametrize(
    "title",
    [
        "IT Junior",
        "Junior IT",
        "Junior IT Support Specialist | No Experience Required",
        "Junior System Administrator (On-Prem)",
        "Junior Helpdesk Technician",
        "IT Associate",
    ],
)
def test_junior_it_titles_get_top_score(classifier: Classifier, title: str) -> None:
    job = make_job(title)
    assert classifier.classify(job)
    assert (job.cv, job.score) == ("IT_Support", 3)


def test_junior_it_keywords_are_searched() -> None:
    keywords = load_config()["linkedin"]["keywords"]
    for keyword in ["Junior IT", "IT Junior", "IT technician", "Desktop support"]:
        assert keyword in keywords
