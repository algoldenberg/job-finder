from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from job_collector.models import Job
from job_collector.output import write_csv
from job_collector.store import Store

NOW = datetime(2026, 11, 23, 5, 0, tzinfo=UTC)


def job(url: str, company: str = "Acme", title: str = "NOC Engineer", source: str = "LinkedIn"):
    return Job(source, url, title, company, "Tel Aviv", url)


@pytest.fixture
def store(tmp_path: Path):
    with Store(tmp_path / "state.db") as s:
        yield s


def test_first_run_uses_default_window(store: Store) -> None:
    assert store.last_success() is None
    assert store.window_start(NOW, default=timedelta(hours=24)) == NOW - timedelta(hours=24)


def test_window_starts_at_last_success_with_overlap(store: Store) -> None:
    yesterday = NOW - timedelta(hours=24)
    run_id = store.start_run(yesterday, yesterday - timedelta(hours=24))
    store.finish_run(run_id, "ok", found=5, delivered=3)
    failed = store.start_run(NOW - timedelta(hours=2), yesterday)
    store.finish_run(failed, "error", error="boom")
    assert store.last_success() == yesterday
    assert store.window_start(NOW, timedelta(hours=24)) == yesterday - timedelta(hours=1)


def test_window_is_capped_at_seven_days(store: Store) -> None:
    long_ago = NOW - timedelta(days=30)
    store.finish_run(store.start_run(long_ago, long_ago), "ok")
    assert store.window_start(NOW, timedelta(hours=24)) == NOW - timedelta(days=7)


def test_remembered_jobs_are_filtered_by_url_and_key(store: Store) -> None:
    store.remember([job("https://l/1", "Cato Networks", "DevOps Engineer")], NOW)
    same_url = job("https://l/1")
    same_job_other_site = job("https://g/9", "Cato Networks", "DevOps Engineer", "Greenhouse")
    fresh = job("https://l/2", "Cato Networks", "NOC Engineer")
    assert store.filter_new([same_url, same_job_other_site, fresh]) == [fresh]


def test_hidden_company_matches_by_url_only(store: Store) -> None:
    store.remember([job("https://l/1", "(hidden)", "Technician")], NOW)
    assert len(store.filter_new([job("https://l/2", "(hidden)", "Technician")])) == 1


def test_seed_from_csv(store: Store, tmp_path: Path) -> None:
    csv_path = tmp_path / "jobs.csv"
    write_csv([job("https://l/1"), job("https://l/2", title="Help Desk")], csv_path, added=NOW)
    assert store.seed_from_csv(csv_path, NOW) == 2
    assert store.last_success() == NOW
    assert store.filter_new([job("https://l/1"), job("https://l/3", title="SRE")])[0].url == (
        "https://l/3"
    )
