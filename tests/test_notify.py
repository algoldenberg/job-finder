from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import requests

from job_collector.httpclient import Stats
from job_collector.models import Job
from job_collector.notify import Telegram, build_error, build_summary

IL = ZoneInfo("Asia/Jerusalem")
ADDED = datetime(2026, 11, 23, 7, 5, tzinfo=IL)
SINCE = datetime(2026, 11, 22, 14, 32, tzinfo=UTC)


def job(title: str, company: str, cv: str, score: int, source="LinkedIn", notes=()) -> Job:
    return Job(
        source,
        title,
        title,
        company,
        "Tel Aviv",
        f"https://l/{title}",
        cv=cv,
        score=score,
        notes=list(notes),
    )


JOBS = [
    job("Junior IT Support", "AT&T", "IT_Support", 3, notes=["Hebrew required"]),
    job("Help Desk Engineer", "PassportCard", "IT_Support", 2, notes=["shift work"]),
    job("NOC Engineer", "Cato", "NOC", 2, source="Greenhouse"),
    job("DevOps Engineer", "Zesty", "DevOps", 1, notes=["likely too senior"]),
]


def test_summary_counts_and_top_picks() -> None:
    stats = Stats(requests=96, retries=3, rate_limited=3, failures=0)
    text = build_summary(JOBS, stats, SINCE, ADDED, "https://sheet/1")
    assert "<b>Job Finder</b> — Mon 23 Nov, 07:05" in text
    assert "New jobs: <b>4</b> (since Sun 22 Nov 16:32)" in text
    assert "By CV: IT_Support 2 · NOC 1 · DevOps 1" in text
    assert "By score: ★3 1 · ★2 2 · ★1 1" in text
    assert "By source: LinkedIn 3 · Greenhouse 1" in text
    assert "Flags: Hebrew 1 · shifts 1 · too senior 1" in text
    assert "Junior IT Support</a> — AT&amp;T (IT_Support)" in text
    assert "DevOps Engineer</a>" not in text  # score 1 is not a top pick
    assert "Requests 96 · 429 3 · failed 0" in text
    assert "rate limiting" not in text
    assert '<a href="https://sheet/1">Open the sheet</a>' in text


def test_summary_without_jobs_warns_about_rate_limit() -> None:
    text = build_summary([], Stats(requests=40, rate_limited=12), SINCE, ADDED, None)
    assert "No new jobs since Sun 22 Nov 16:32." in text
    assert "LinkedIn is rate limiting" in text
    assert "Open the sheet" not in text


def test_error_message_is_escaped() -> None:
    text = build_error(RuntimeError("bad <html> & stuff"), SINCE)
    assert "RuntimeError: bad &lt;html&gt; &amp; stuff" in text
    assert "next run will try again" in text


class FakeSession:
    def __init__(self, status: int = 200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.posts: list = []

    def post(self, url, data, timeout):
        self.posts.append((url, data))
        if self.error:
            raise self.error
        return type("Response", (), {"status_code": self.status})()


def test_send_posts_html_message() -> None:
    session = FakeSession()
    assert Telegram("123:abc", "42", session).send("hi")
    url, data = session.posts[0]
    assert url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert data == {
        "chat_id": "42",
        "text": "hi",
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }


def test_send_failures_do_not_raise() -> None:
    assert not Telegram("t", "1", FakeSession(status=400)).send("x")
    assert not Telegram("t", "1", FakeSession(error=requests.ConnectionError())).send("x")


def test_from_env(monkeypatch) -> None:
    assert Telegram.from_env() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    bot = Telegram.from_env()
    assert (bot.token, bot.chat_id) == ("123:abc", "42")
