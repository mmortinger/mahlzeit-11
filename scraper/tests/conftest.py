from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REF = date(2026, 11, 12)  # Donnerstag, KW46 – Tag, an dem die Fixtures abgerufen wurden


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    from scraper import __main__ as runner
    monkeypatch.setattr(runner, "RETRY_DELAY", 0)
