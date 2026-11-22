"""Google Sheets output: one tab per Sunday-Thursday week, rows are only ever appended."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from job_collector.models import Job
from job_collector.output import COLUMNS, sort_jobs, to_row

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]  # this sheet only, no Drive access
AUTO_COLUMNS = COLUMNS.index("Status")  # the script writes up to Notes; the rest is manual
FORMULA_START = ("=", "+", "-", "@")


def week_start(day: date) -> date:
    """Sunday of the week that contains `day` (Friday and Saturday belong to the past week)."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def week_title(day: date) -> str:
    """'22–26 Nov', or '29 Nov–3 Dec' when the week crosses a month."""
    start = week_start(day)
    end = start + timedelta(days=4)
    if start.month == end.month:
        return f"{start.day}–{end.day} {end:%b}"
    return f"{start.day} {start:%b}–{end.day} {end:%b}"


def _safe(value: str) -> str:
    """Stop text like '+972...' or '=x' from being read as a formula."""
    return f"'{value}" if value.startswith(FORMULA_START) else value


def sheet_rows(jobs: list[Job], added: datetime) -> list[list[str | int]]:
    rows = []
    for job in sort_jobs(jobs):
        row: list[str | int] = [_safe(v) for v in to_row(job, added)[:AUTO_COLUMNS]]
        row[COLUMNS.index("Score")] = job.score
        rows.append(row)
    return rows


class SheetWriter:
    def __init__(self, spreadsheet) -> None:
        self.spreadsheet = spreadsheet

    @classmethod
    def connect(cls, spreadsheet_id: str, credentials: Path) -> "SheetWriter":
        import gspread  # imported here so tests and CSV-only runs do not need Google auth

        client = gspread.service_account(filename=str(credentials), scopes=SCOPES)
        return cls(client.open_by_key(spreadsheet_id))

    def week_tab(self, day: date):
        """Return this week's tab, creating it as a formatted copy of the newest tab."""
        title = week_title(day)
        worksheets = self.spreadsheet.worksheets()
        for worksheet in worksheets:
            if worksheet.title == title:
                return worksheet
        if worksheets:
            template = worksheets[0]
            tab = self.spreadsheet.duplicate_sheet(
                template.id, insert_sheet_index=0, new_sheet_name=title
            )
            tab.batch_clear(["A2:Z"])
            log.info("created tab %r from %r", title, template.title)
        else:
            tab = self.spreadsheet.add_worksheet(title, rows=1000, cols=len(COLUMNS), index=0)
            tab.append_rows([COLUMNS])
            log.info("created tab %r", title)
        return tab

    def append(self, jobs: list[Job], added: datetime) -> str:
        """Append jobs to this week's tab and return the tab URL."""
        tab = self.week_tab(added.date())
        if jobs:
            tab.append_rows(
                sheet_rows(jobs, added), value_input_option="USER_ENTERED", table_range="A1"
            )
        log.info("appended %d rows to %r", len(jobs), tab.title)
        return tab.url
