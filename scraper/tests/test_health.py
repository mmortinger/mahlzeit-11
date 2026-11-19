from datetime import date, datetime

from scraper import __main__ as runner
from scraper import health
from scraper.common import VIENNA


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=VIENNA)


def restaurant(id_, dates=("2026-11-12",), **extra):
    r = {"id": id_, "name": id_.title(), "stale": False, "error": None,
         "days": [{"date": d, "items": [{"label": "M", "name": "X"}]} for d in dates]}
    r.update(extra)
    return r


def msgs(problems):
    return [(p.level, p.restaurant) for p in problems]


THU_NOON = at("2026-11-12T12:00")


def test_all_ok():
    data = {"restaurants": [restaurant("a"), restaurant("b")]}
    assert health.check(data, THU_NOON) == []


def test_stale_is_error_any_time():
    data = {"restaurants": [restaurant("a", stale=True, error="HTTPError: 503")]}
    for t in ("2026-11-12T07:30", "2026-11-12T12:00", "2026-11-14T12:00"):
        probs = health.check(data, at(t))
        assert msgs(probs) == [("Fehler", "A")] and "503" in probs[0].message


def test_missing_today_only_warns_from_11():
    data = {"restaurants": [restaurant("a", dates=("2026-11-11",))]}
    assert health.check(data, at("2026-11-12T09:30")) == []  # früher Lauf: Seite evtl. noch nicht aktualisiert
    assert msgs(health.check(data, at("2026-11-12T11:15"))) == [("Warnung", "A")]


def test_no_warning_on_weekend_or_holiday():
    data = {"restaurants": [restaurant("a", dates=())]}
    assert health.check(data, at("2026-11-14T12:00")) == []  # Samstag
    assert health.check(data, at("2026-12-08T12:00")) == []  # Mariä Empfängnis (Dienstag)
    assert health.check(data, at("2026-05-14T12:00")) == []  # Christi Himmelfahrt 2026


def test_flyer_only_is_warning():
    data = {"restaurants": [restaurant("interspar", dates=(), flyer_url="https://x")]}
    assert msgs(health.check(data, at("2026-11-12T08:00"))) == [("Warnung", "Interspar")]


def test_holidays():
    assert health._easter(2026) == date(2026, 4, 5)
    assert health._easter(2027) == date(2027, 3, 28)
    h = health.austrian_holidays(2026)
    assert {date(2026, 4, 6), date(2026, 5, 25), date(2026, 6, 4), date(2026, 10, 26)} <= h
    assert not health.is_workday(date(2026, 12, 25)) and health.is_workday(date(2026, 11, 12))


def test_report_to_github(tmp_path, monkeypatch):
    out, summary = tmp_path / "out", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    probs = [health.Problem("Fehler", "Fruga Vital", "Abruf fehlgeschlagen")]
    runner.report_to_github(probs)
    text = out.read_text(encoding="utf-8")
    assert "problems=1\n" in text
    assert "problem_text<<__EOF__\nFehler – Fruga Vital: Abruf fehlgeschlagen\n__EOF__\n" in text
    assert "Fruga Vital" in summary.read_text(encoding="utf-8")

    out.unlink()
    runner.report_to_github([])
    assert "problems=0\n" in out.read_text(encoding="utf-8")


def test_no_warning_when_source_already_shows_next_week():
    data = {"restaurants": [restaurant("lercherl", dates=("2026-11-16", "2026-11-17"))]}
    assert health.check(data, at("2026-11-13T15:47")) == []



BLOCKED = "BlockedError: Bot-Schutz der Website (Seite „Einen Moment bitte …“)"


def test_blocked_with_todays_data_is_no_problem():
    data = {"restaurants": [restaurant("osfizio", dates=("2026-11-12",), stale=True, error=BLOCKED)]}
    assert health.check(data, THU_NOON) == []
    assert health.check(data, at("2026-11-12T09:00")) == []


def test_blocked_without_todays_data_warns_from_11():
    data = {"restaurants": [restaurant("osfizio", dates=("2026-11-11",), stale=True, error=BLOCKED)]}
    assert health.check(data, at("2026-11-12T09:00")) == []
    probs = health.check(data, THU_NOON)
    assert msgs(probs) == [("Warnung", "Osfizio")] and "Bot-Schutz" in probs[0].message
