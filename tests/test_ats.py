from datetime import UTC, datetime

from job_collector import ats
from job_collector.config import load_config

SINCE = datetime(2026, 11, 20, 5, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeClient:
    """Maps a URL to a list of payloads returned one by one."""

    def __init__(self, routes: dict) -> None:
        self.routes = {url: list(payloads) for url, payloads in routes.items()}
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        payloads = self.routes.get(url)
        return FakeResponse(payloads.pop(0)) if payloads else None


GH_URL = ats.GREENHOUSE_URL.format(slug="acme")
GH_PAYLOAD = {
    "jobs": [
        {
            "id": 1,
            "title": "DevOps Engineer ",
            "location": {"name": "Tel Aviv District, Israel"},
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "first_published": "2026-11-21T08:00:00-05:00",
            "updated_at": "2026-11-21T08:00:00-05:00",
        },
        {
            "id": 2,
            "title": "Old Israel role",
            "location": {"name": "Tel Aviv District, Israel"},
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/2",
            "first_published": "2025-05-01T08:00:00-04:00",
            "updated_at": "2026-11-21T08:00:00-05:00",
        },
        {
            "id": 3,
            "title": "New role abroad",
            "location": {"name": "Montreal, Quebec, Canada"},
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/3",
            "first_published": "2026-11-21T08:00:00-05:00",
            "updated_at": "2026-11-21T08:00:00-05:00",
        },
    ]
}


def test_greenhouse_uses_first_published_and_filters() -> None:
    client = FakeClient({GH_URL: [GH_PAYLOAD]})
    jobs = ats.collect(client, {"greenhouse": {"Acme": "acme"}}, "israel|tel aviv", SINCE)
    assert [(j.job_id, j.title, j.company) for j in jobs] == [("1", "DevOps Engineer", "Acme")]


def test_lever_country_code_marks_israel() -> None:
    url = ats.LEVER_URL.format(slug="acme")
    payload = [
        {
            "id": "abc",
            "text": "NOC Engineer",
            "categories": {"location": "Herzliya", "allLocations": ["Herzliya"]},
            "country": "IL",
            "hostedUrl": "https://jobs.lever.co/acme/abc",
            "createdAt": int(datetime(2026, 11, 21, tzinfo=UTC).timestamp() * 1000),
            "descriptionPlain": "Shifts 24/7",
        }
    ]
    client = FakeClient({url: [payload]})
    [job] = ats.collect(client, {"lever": {"Acme": "acme"}}, "israel", SINCE)
    assert job.location == "Herzliya, Israel"
    assert job.description == "Shifts 24/7"
    assert client.calls[0][1] == {"mode": "json"}


def test_smartrecruiters_paginates() -> None:
    url = ats.SMARTRECRUITERS_URL.format(slug="Acme2")

    def item(i: int) -> dict:
        return {
            "id": str(i),
            "name": f"Role {i}",
            "location": {"city": "Tel Aviv", "country": "il"},
            "releasedDate": "2026-11-22T11:38:43.633Z",
        }

    first = {"totalFound": 101, "content": [item(i) for i in range(100)]}
    second = {"totalFound": 101, "content": [item(100)]}
    client = FakeClient({url: [first, second]})
    jobs = ats.collect(client, {"smartrecruiters": {"Acme": "Acme2"}}, "israel", SINCE)
    assert len(jobs) == 101
    assert jobs[0].location == "Tel Aviv, Israel"
    assert jobs[0].url == "https://jobs.smartrecruiters.com/Acme2/0"
    assert [c[1]["offset"] for c in client.calls] == [0, 100]


def test_failures_and_unknown_platform_are_skipped() -> None:
    client = FakeClient({GH_URL: [ValueError("not json")]})
    config = {"greenhouse": {"Acme": "acme", "Missing": "missing"}, "workday": {"X": "x"}}
    assert ats.collect(client, config, "israel", SINCE) == []


def test_config_location_pattern_survives_yaml_folding() -> None:
    matcher = ats.israel_matcher(load_config()["israel_locations"])
    for place in ["Be'er Sheva", "Tel-Aviv", "Hod Hasharon", "Netanya, Center", "Tel Aviv, Israel"]:
        assert matcher.search(place), place
    assert not matcher.search("Montreal, Quebec, Canada")
