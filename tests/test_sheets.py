from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from job_collector.models import Job
from job_collector.output import COLUMNS
from job_collector.sheets import SheetWriter, sheet_rows, week_start, week_title

IL = ZoneInfo("Asia/Jerusalem")


@pytest.mark.parametrize(
    ("day", "start"),
    [
        (date(2026, 11, 22), date(2026, 11, 22)),  # Sunday
        (date(2026, 11, 26), date(2026, 11, 22)),  # Thursday
        (date(2026, 11, 28), date(2026, 11, 22)),  # Saturday belongs to the past week
        (date(2026, 11, 29), date(2026, 11, 29)),  # next Sunday
    ],
)
def test_week_start(day: date, start: date) -> None:
    assert week_start(day) == start


def test_week_title() -> None:
    assert week_title(date(2026, 11, 24)) == "22–26 Nov"
    assert week_title(date(2026, 11, 30)) == "29 Nov–3 Dec"


def test_sheet_rows_keep_manual_columns_and_escape_formulas() -> None:
    job = Job("LinkedIn", "1", "=SUM(A1)", "+972 Ltd", "Tel Aviv", "https://l/1", cv="NOC", score=3)
    [row] = sheet_rows([job], datetime(2026, 11, 23, 7, 0, tzinfo=IL))
    assert len(row) == COLUMNS.index("Status")
    assert row[2:4] == ["'+972 Ltd", "'=SUM(A1)"]
    assert row[COLUMNS.index("Score")] == 3


class FakeTab:
    def __init__(self, title: str, tab_id: int) -> None:
        self.title = title
        self.id = tab_id
        self.url = f"https://sheet#gid={tab_id}"
        self.appended: list = []
        self.cleared: list = []

    def append_rows(self, rows, **kwargs) -> None:
        self.appended.append((rows, kwargs))

    def batch_clear(self, ranges) -> None:
        self.cleared.append(ranges)


class FakeSpreadsheet:
    def __init__(self, titles: list[str]) -> None:
        self.tabs = [FakeTab(t, i) for i, t in enumerate(titles)]

    def worksheets(self):
        return list(self.tabs)

    def duplicate_sheet(self, source_id, insert_sheet_index, new_sheet_name):
        tab = FakeTab(new_sheet_name, 100 + len(self.tabs))
        self.tabs.insert(insert_sheet_index, tab)
        return tab

    def add_worksheet(self, title, rows, cols, index):
        tab = FakeTab(title, 200)
        self.tabs.insert(index, tab)
        return tab


JOB = Job("Greenhouse", "1", "NOC Engineer", "Acme", "Herzliya, Israel", "https://g/1", score=2)
MONDAY = datetime(2026, 11, 23, 7, 0, tzinfo=IL)


def test_appends_to_existing_week_tab() -> None:
    sheet = FakeSpreadsheet(["22–26 Nov"])
    url = SheetWriter(sheet).append([JOB], MONDAY)
    tab = sheet.tabs[0]
    assert url == tab.url
    rows, kwargs = tab.appended[0]
    assert rows[0][2:4] == ["Acme", "NOC Engineer"]
    assert kwargs["value_input_option"] == "USER_ENTERED"
    assert tab.cleared == []


def test_new_week_copies_newest_tab_and_clears_rows() -> None:
    sheet = FakeSpreadsheet(["22–26 Nov"])
    SheetWriter(sheet).append([JOB], datetime(2026, 11, 29, 7, 0, tzinfo=IL))
    assert [t.title for t in sheet.tabs] == ["29 Nov–3 Dec", "22–26 Nov"]
    assert sheet.tabs[0].cleared == [["A2:Z"]]
    assert sheet.tabs[1].appended == []


def test_empty_spreadsheet_gets_header() -> None:
    sheet = FakeSpreadsheet([])
    SheetWriter(sheet).append([], MONDAY)
    assert sheet.tabs[0].title == "22–26 Nov"
    assert sheet.tabs[0].appended[0][0] == [COLUMNS]
