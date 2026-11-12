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
