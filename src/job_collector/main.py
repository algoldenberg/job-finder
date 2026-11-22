"""Entry point: collect, filter, deduplicate, enrich and write the results."""

import argparse
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from job_collector import ats, linkedin
from job_collector.classify import Classifier
from job_collector.config import load_config
from job_collector.dedupe import dedupe
from job_collector.enrich import enrich
from job_collector.httpclient import HttpClient
from job_collector.models import Job
from job_collector.notify import Telegram, build_error, build_summary
from job_collector.output import write_csv
from job_collector.sheets import SheetWriter
from job_collector.store import Store

log = logging.getLogger("job_collector")


def collect(config: dict, since: datetime, client: HttpClient, now: datetime) -> list[Job]:
    """Run every source and return classified, deduplicated and enriched jobs."""
    found: list[Job] = []
    found += ats.collect(client, config.get("ats", {}), config["israel_locations"], since)

    li_settings = config.get("linkedin", {})
    if li_settings.get("enabled"):
        window = max(int((now - since).total_seconds()), 3600)
        found += linkedin.search(client, li_settings, window)

    classifier = Classifier.from_config(config)
    kept = dedupe([job for job in found if classifier.classify(job)])
    log.info("found %d, kept %d after filter and dedupe", len(found), len(kept))

    if li_settings.get("enabled") and li_settings.get("fetch_descriptions"):
        for index, job in enumerate(j for j in kept if j.source == "LinkedIn"):
            if index:
                client.pause(li_settings["description_delay_seconds"])
            linkedin.fetch_description(client, job)

    max_years = config["filters"]["max_years_experience"]
    for job in kept:
        enrich(job, max_years)
    return kept


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--hours", type=float, help="look back this many hours (default: since the last run)"
    )
    window.add_argument(
        "--since", type=datetime.fromisoformat, help="ISO time, e.g. 2026-11-20T07:00+02:00"
    )
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--out", type=Path, default=Path("data/jobs.csv"), help="CSV output path")
    parser.add_argument("--state", type=Path, default=Path("data/state.db"), help="SQLite state")
    parser.add_argument("--seed-from", type=Path, help="mark jobs in this CSV as seen and exit")
    parser.add_argument("--no-linkedin", action="store_true", help="skip LinkedIn")
    parser.add_argument("--no-sheet", action="store_true", help="write CSV only")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    if args.no_linkedin:
        config.setdefault("linkedin", {})["enabled"] = False

    now = datetime.now(UTC)
    with Store(args.state) as store:
        if args.seed_from:
            count = store.seed_from_csv(args.seed_from, now)
            log.info("seeded %d jobs from %s", count, args.seed_from)
            return 0
        return run(args, config, store, now)


def run(args: argparse.Namespace, config: dict, store: Store, now: datetime) -> int:
    if args.since:
        since = args.since if args.since.tzinfo else args.since.replace(tzinfo=UTC)
    elif args.hours:
        since = now - timedelta(hours=args.hours)
    else:
        since = store.window_start(now, default=timedelta(hours=24))
    log.info("collecting jobs posted since %s", since.isoformat(timespec="minutes"))

    client = HttpClient()
    telegram = Telegram.from_env()
    sheet_url = None
    run_id = store.start_run(now, since)
    try:
        jobs = collect(config, since, client, now)
        new_jobs = store.filter_new(jobs)
        log.info("%d of %d jobs are new", len(new_jobs), len(jobs))
        added = now.astimezone(ZoneInfo(config.get("timezone", "Asia/Jerusalem")))
        write_csv(new_jobs, args.out, added=added)
        sheet_id = os.environ.get("SHEET_ID", "").strip()
        if sheet_id and not args.no_sheet:
            credentials = Path(
                os.environ.get("GOOGLE_CREDENTIALS", "credentials/service-account.json")
            )
            sheet_url = SheetWriter.connect(sheet_id, credentials).append(new_jobs, added)
        else:
            log.info("SHEET_ID not set or --no-sheet given: CSV only")
        store.remember(new_jobs, now)
    except Exception as exc:
        log.exception("run failed")
        store.finish_run(run_id, "error", error=f"{type(exc).__name__}: {exc}")
        if telegram:
            telegram.send(build_error(exc, since))
        return 1

    s = client.stats
    store.finish_run(
        run_id,
        "ok",
        found=len(jobs),
        delivered=len(new_jobs),
        requests=s.requests,
        rate_limited=s.rate_limited,
        failures=s.failures,
    )
    log.info(
        "done: %d new jobs -> %s | requests %d, retries %d, rate limited %d, failed %d",
        len(new_jobs),
        args.out,
        s.requests,
        s.retries,
        s.rate_limited,
        s.failures,
    )
    if telegram:
        telegram.send(build_summary(new_jobs, s, since, added, sheet_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
