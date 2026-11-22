import csv
from datetime import UTC, datetime, timedelta

from job_collector import main as app
from job_collector.config import load_config
from job_collector.models import Job
from job_collector.output import COLUMNS, short_city

NOW = datetime(2026, 11, 22, 5, 0, tzinfo=UTC)


class FakeClient:
    def __init__(self) -> None:
        self.pauses: list = []

    def pause(self, bounds) -> None:
        self.pauses.append(bounds)


def li_job(job_id: str, title: str, company: str) -> Job:
    return Job(
        "LinkedIn",
        job_id,
        title,
        company,
        "Tel Aviv-Yafo, Tel Aviv District, Israel",
        f"https://www.linkedin.com/jobs/view/{job_id}",
    )


def test_pipeline_filters_dedupes_and_enriches(monkeypatch) -> None:
    gh = Job(
        "Greenhouse",
        "9",
        "DevOps Engineer",
        "Cato Networks",
        "Tel Aviv District, Israel",
        "https://g/9",
        posted=NOW,
    )
    monkeypatch.setattr(app.ats, "collect", lambda *a, **k: [gh])
    linkedin_jobs = [
        li_job("1", "Junior IT Support", "Acme"),
        li_job("2", "Senior DevOps Engineer", "Acme"),
        li_job("3", "DevOps Engineer", "Cato Networks"),
    ]
    windows = []
    monkeypatch.setattr(
        app.linkedin, "search", lambda client, s, w: windows.append(w) or list(linkedin_jobs)
    )

    def fake_description(client, job):
        job.description = "Fluent Hebrew, 2+ years"

    monkeypatch.setattr(app.linkedin, "fetch_description", fake_description)

    jobs = app.collect(load_config(), NOW - timedelta(hours=24), FakeClient(), NOW)

    assert windows == [86400]
    assert sorted((j.source, j.title) for j in jobs) == [
        ("Greenhouse", "DevOps Engineer"),
        ("LinkedIn", "Junior IT Support"),
    ]
    cato = next(j for j in jobs if j.company == "Cato Networks")
    assert cato.also_in == ["LinkedIn"]
    support = next(j for j in jobs if j.source == "LinkedIn")
    assert (support.cv, support.score) == ("IT_Support", 3)
    assert support.notes == ["experience 2+ y", "Hebrew required"]


def test_cli_writes_csv(monkeypatch, tmp_path) -> None:
    job = Job(
        "Greenhouse",
        "1",
        "NOC Engineer",
        "Acme",
        "Herzliya, Israel",
        "https://g/1",
        posted=NOW,
        cv="NOC",
        score=2,
    )
    monkeypatch.setattr(app, "collect", lambda *a, **k: [job])
    out = tmp_path / "jobs.csv"
    args = ["--no-linkedin", "--out", str(out), "--state", str(tmp_path / "state.db")]
    assert app.main(args) == 0
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == COLUMNS
    assert rows[1][2:9] == [
        "Acme",
        "NOC Engineer",
        "Herzliya",
        "https://g/1",
        "Greenhouse",
        "NOC",
        "2",
    ]


def test_short_city() -> None:
    assert short_city("Tel Aviv-Yafo, Tel Aviv District, Israel") == "Tel Aviv-Yafo, Tel Aviv"
    assert short_city("Tel Aviv, il") == "Tel Aviv"
    assert short_city("Herzliya") == "Herzliya"


def test_second_run_skips_known_jobs_and_failed_run_is_recorded(monkeypatch, tmp_path) -> None:
    jobs = [
        Job("Greenhouse", "1", "NOC Engineer", "Acme", "Herzliya", "https://g/1", posted=NOW),
        Job("Greenhouse", "2", "Help Desk", "Acme", "Herzliya", "https://g/2", posted=NOW),
    ]
    monkeypatch.setattr(app, "collect", lambda *a, **k: list(jobs))
    out = tmp_path / "jobs.csv"
    args = ["--no-linkedin", "--out", str(out), "--state", str(tmp_path / "state.db")]

    assert app.main(args) == 0
    assert len(list(csv.reader(out.open(encoding="utf-8")))) == 3

    jobs.append(Job("Greenhouse", "3", "SRE", "Acme", "Herzliya", "https://g/3", posted=NOW))
    assert app.main(args) == 0
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert [r[3] for r in rows[1:]] == ["SRE"]

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(app, "collect", boom)
    assert app.main(args) == 1


def test_sheet_is_written_before_jobs_are_remembered(monkeypatch, tmp_path) -> None:
    job = Job("Greenhouse", "1", "NOC Engineer", "Acme", "Herzliya", "https://g/1", posted=NOW)
    monkeypatch.setattr(app, "collect", lambda *a, **k: [job])
    calls = []

    class FakeWriter:
        def append(self, jobs, added):
            calls.append((len(jobs), added.tzinfo.key))
            if len(calls) == 1:
                raise RuntimeError("Sheets API unavailable")
            return "https://sheet"

    monkeypatch.setattr(app.SheetWriter, "connect", lambda sheet_id, credentials: FakeWriter())
    monkeypatch.setenv("SHEET_ID", "abc")
    args = ["--no-linkedin", "--out", str(tmp_path / "jobs.csv"), "--state", str(tmp_path / "s.db")]

    assert app.main(args) == 1  # sheet failed, so the job is not remembered
    assert app.main(args) == 0  # retried on the next run
    assert calls == [(1, "Asia/Jerusalem"), (1, "Asia/Jerusalem")]
