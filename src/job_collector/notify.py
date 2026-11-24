"""Telegram notifications: a short summary after every run and an alert when a run fails."""

import html
import logging
import os
from collections import Counter
from datetime import datetime
from typing import Self

import requests

from job_collector.httpclient import Stats
from job_collector.models import Job
from job_collector.output import sort_jobs

log = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TOP_PICKS = 5
RATE_LIMIT_SHARE = 0.25  # warn when more than a quarter of requests were answered with 429


def _counts(values: list[str]) -> str:
    return " · ".join(f"{name} {count}" for name, count in Counter(values).most_common())


def _score_counts(jobs: list[Job]) -> str:
    counts = Counter(j.score for j in jobs)
    return " · ".join(f"★{score} {counts[score]}" for score in sorted(counts, reverse=True))


def _flags(jobs: list[Job]) -> str:
    notes = [note for job in jobs for note in job.notes]
    flags = {
        "Hebrew": sum(n in ("Hebrew required", "posting in Hebrew") for n in notes),
        "shifts": notes.count("shift work"),
        "too senior": notes.count("likely too senior"),
    }
    return " · ".join(f"{name} {count}" for name, count in flags.items() if count)


def build_summary(
    jobs: list[Job], stats: Stats, since: datetime, added: datetime, sheet_url: str | None
) -> str:
    when = added.strftime("%a %d %b, %H:%M")
    since_text = since.astimezone(added.tzinfo).strftime("%a %d %b %H:%M")
    lines = [f"<b>Job Finder</b> — {when}"]
    if not jobs:
        lines.append(f"No new jobs since {since_text}.")
    else:
        lines += [
            f"New jobs: <b>{len(jobs)}</b> (since {since_text})",
            f"By CV: {_counts([j.cv for j in jobs])}",
            f"By score: {_score_counts(jobs)}",
            f"By source: {_counts([j.source for j in jobs])}",
        ]
        if flags := _flags(jobs):
            lines.append(f"Flags: {flags}")
        picks = [j for j in sort_jobs(jobs) if j.score >= 2][:TOP_PICKS]
        if picks:
            lines.append("")
            lines.append("<b>Top picks</b>")
            lines += [
                f'• <a href="{html.escape(j.url)}">{html.escape(j.title)}</a>'
                f" — {html.escape(j.company)} ({j.cv})"
                for j in picks
            ]
    lines.append("")
    lines.append(f"Requests {stats.requests} · 429 {stats.rate_limited} · failed {stats.failures}")
    if stats.failures:
        lines.append("⚠️ Some requests failed even after retries, results may be incomplete.")
    elif stats.requests and stats.rate_limited / stats.requests > RATE_LIMIT_SHARE:
        lines.append("⚠️ LinkedIn is rate limiting this IP, check the logs.")
    if sheet_url:
        lines.append(f'<a href="{html.escape(sheet_url)}">Open the sheet</a>')
    return "\n".join(lines)


def build_error(error: BaseException, since: datetime) -> str:
    text = html.escape(f"{type(error).__name__}: {error}")[:500]
    return (
        "⚠️ <b>Job Finder run failed</b>\n"
        f"Window started {since:%Y-%m-%d %H:%M} UTC.\n"
        f"<code>{text}</code>\n"
        "Nothing was marked as seen, the next run will try again."
    )


class Telegram:
    def __init__(self, token: str, chat_id: str, session: requests.Session | None = None) -> None:
        self.token = token
        self.chat_id = chat_id
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls) -> Self | None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            log.info("Telegram is not configured, skipping notifications")
            return None
        return cls(token, chat_id)

    def send(self, text: str) -> bool:
        """Send a message. A failed notification is logged and never fails the run."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            response = self.session.post(API_URL.format(token=self.token), data=payload, timeout=20)
        except requests.RequestException as exc:
            log.warning("telegram request failed: %s", type(exc).__name__)
            return False
        if response.status_code != 200:
            log.warning("telegram answered HTTP %s", response.status_code)
            return False
        return True
