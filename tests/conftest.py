import pytest

from job_collector import main as app


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Never read the developer's .env in tests, so no test can reach the real sheet or bot."""
    monkeypatch.setattr(app, "load_dotenv", lambda *a, **k: None)
    for name in ("SHEET_ID", "GOOGLE_CREDENTIALS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
