from datetime import UTC, datetime

from job_collector import linkedin
from job_collector.models import Job


def card(job_id: str, title: str, company: str | None, date: str = "2026-11-22") -> str:
    if company is None:
        subtitle = '<h4 class="base-search-card__subtitle"> </h4>'
    else:
        subtitle = (
            '<h4 class="base-search-card__subtitle">'
            f'<a class="hidden-nested-link" href="/company/x"> {company} </a>'
            "</h4>"
        )
    return (
        f'<li><div class="base-card" data-entity-urn="urn:li:jobPosting:{job_id}">'
        f'<h3 class="base-search-card__title"> {title} </h3>{subtitle}'
        '<span class="job-search-card__location"> Tel Aviv-Yafo, Israel </span>'
        f'<time class="job-search-card__listdate" datetime="{date}"> 1 day ago </time>'
        "</div></li>"
    )


def page(*cards: str) -> str:
    return "".join(cards)


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeClient:
    def __init__(self, pages: list[str]) -> None:
        self.pages = list(pages)
        self.calls: list[dict] = []
        self.pauses: list = []

    def get(self, url, params=None):
        self.calls.append(params or {})
        return FakeResponse(self.pages.pop(0)) if self.pages else FakeResponse("")

    def pause(self, bounds) -> None:
        self.pauses.append(bounds)


SETTINGS = {
    "keywords": ["DevOps"],
    "location": "Israel",
    "page_size": 10,
    "max_pages": 5,
    "delay_seconds": [3, 7],
    "keyword_delay_seconds": [6, 12],
}


def test_parse_card_fields() -> None:
    [job] = linkedin.parse_cards(page(card("111", "DevOps Engineer", "Check Point &amp; Co")))
    assert job.job_id == "111"
    assert job.title == "DevOps Engineer"
    assert job.company == "Check Point & Co"
    assert job.location == "Tel Aviv-Yafo, Israel"
    assert job.url == "https://www.linkedin.com/jobs/view/111"
    assert job.posted == datetime(2026, 11, 22, tzinfo=UTC)


def test_hidden_company_does_not_leak_markup() -> None:
    [job] = linkedin.parse_cards(page(card("222", "Technician", None)))
    assert job.company == "(hidden)"


def test_search_stops_on_empty_page_and_sends_params() -> None:
    client = FakeClient([page(card("1", "A", "X"), card("2", "B", "X")), ""])
    jobs = linkedin.search(client, SETTINGS, window_seconds=86400)
    assert [j.job_id for j in jobs] == ["1", "2"]
    assert len(client.calls) == 2
    assert client.calls[0] == {
        "keywords": "DevOps",
        "location": "Israel",
        "f_TPR": "r86400",
        "start": 0,
    }
    assert client.calls[1]["start"] == 10


def test_search_stops_after_two_pages_without_new_jobs() -> None:
    first = page(card("1", "A", "X"))
    client = FakeClient([first, first, first, page(card("9", "Z", "X"))])
    jobs = linkedin.search(client, SETTINGS, window_seconds=3600)
    assert [j.job_id for j in jobs] == ["1"]
    assert len(client.calls) == 3


def test_search_keeps_going_after_one_repeated_page() -> None:
    first = page(card("1", "A", "X"))
    client = FakeClient([first, first, page(card("9", "Z", "X")), ""])
    jobs = linkedin.search(client, SETTINGS, window_seconds=3600)
    assert [j.job_id for j in jobs] == ["1", "9"]


def test_search_dedupes_across_keywords_and_pauses() -> None:
    settings = {**SETTINGS, "keywords": ["DevOps", "SRE"]}
    client = FakeClient(
        [page(card("1", "A", "X")), "", page(card("1", "A", "X"), card("2", "B", "Y"))]
    )
    jobs = linkedin.search(client, settings, window_seconds=3600)
    assert sorted(j.job_id for j in jobs) == ["1", "2"]
    assert [6, 12] in client.pauses
    assert [3, 7] in client.pauses


def test_fetch_description() -> None:
    body = '<div class="show-more-less-html__markup"> <p>Fluent <b>Hebrew</b> required</p> </div>'
    client = FakeClient([body])
    job = Job("LinkedIn", "5", "T", "C", "L", "U")
    linkedin.fetch_description(client, job)
    assert job.description == "Fluent Hebrew required"
