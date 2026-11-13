import json
import types

from scraper import __main__ as runner
from scraper.models import Day, Item, RestaurantMenu


def fake_module(id_, scrape):
    return types.SimpleNamespace(ID=id_, NAME=id_.title(), URL=f"https://{id_}.example", scrape=scrape)


def ok_menu():
    return RestaurantMenu(id="a", name="A", source_url="https://a.example",
                          days=[Day(date="2026-11-12", items=[Item(label="M", name="Suppe", price=5.0)])])


def boom():
    raise RuntimeError("Seite weg")


def test_failure_keeps_old_data_as_stale():
    old = {"id": "b", "name": "B", "days": [{"date": "2026-11-12", "items": []}], "stale": False, "error": None}
    data = runner.build([fake_module("a", ok_menu), fake_module("b", boom)], {"b": old})
    a, b = data["restaurants"]
    assert a["stale"] is False and a["error"] is None and a["fetched_at"]
    assert b["stale"] is True and "Seite weg" in b["error"] and b["days"] == old["days"]


def test_failure_without_old_data():
    data = runner.build([fake_module("b", boom)], {})
    b = data["restaurants"][0]
    assert b["stale"] is True and b["days"] == [] and b["source_url"] == "https://b.example"


def test_empty_result_counts_as_error():
    def empty():
        return RestaurantMenu(id="a", name="A", source_url="x")

    r = runner.build([fake_module("a", empty)], {})["restaurants"][0]
    assert r["stale"] is True and "Keine Menüdaten" in r["error"]


def test_write_only_on_change(tmp_path):
    path = tmp_path / "menu.json"
    data = runner.build([fake_module("a", ok_menu)], {})
    assert runner.write_if_changed(path, data) is True
    again = runner.build([fake_module("a", ok_menu)], {})  # neue Zeitstempel, gleicher Inhalt
    assert runner.write_if_changed(path, again) is False
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["restaurants"][0]["days"][0]["items"][0]["name"] == "Suppe"


def _day(iso, name="X"):
    return {"date": iso, "items": [{"label": "M", "name": name}]}


def test_merge_keeps_today_when_source_switched_to_next_week():
    # Lercherl am Freitagnachmittag: Quelle zeigt schon die Folgewoche
    from datetime import date
    old = {"days": [_day("2026-11-06"), _day("2026-11-12"), _day("2026-11-13"), _day("2026-11-14", "alt")]}
    new = {"days": [_day("2026-11-16"), _day("2026-11-17")]}
    runner._merge_past_days(new, old, today=date(2026, 11, 13))
    # Vorwoche weg, Mo–heute behalten, alte Zukunftstage nicht wiederbeleben
    assert [d["date"] for d in new["days"]] == ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"]


def test_merge_prefers_fresh_data_for_same_day():
    from datetime import date
    old = {"days": [_day("2026-11-13", "alt")]}
    new = {"days": [_day("2026-11-13", "neu")]}
    runner._merge_past_days(new, old, today=date(2026, 11, 13))
    assert [d["items"][0]["name"] for d in new["days"]] == ["neu"]
