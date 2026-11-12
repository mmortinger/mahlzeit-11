from scraper.restaurants import fruga

from .conftest import REF


def test_parse_table(fixture_text):
    menu = fruga.parse(fixture_text("fruga.html"), REF)
    # Vor-Samstag 7.11. wird verworfen, Mo–Sa der aktuellen Woche bleiben
    assert [d.date for d in menu.days] == [f"2026-11-{n:02d}" for n in range(9, 15)]
    fri = menu.days[4]
    assert len(fri.items) == 4
    assert (fri.items[0].name, fri.items[0].price) == ("Kabeljaufilet gebacken mit Erdäpfelsalat", 15.9)
    assert fri.items[3].price == 9.9
    assert menu.subtitle == "Immer zu haben: Surschnitzel, Hühnerschnitzel und Kabeljaufilet"
    assert menu.notes == []  # nicht doppelt als Hinweis


def test_pdf_fallback_matches_table(fixture_text, fixture_bytes):
    table = fruga.parse(fixture_text("fruga.html"), REF).days
    pdf = fruga.parse_pdf(fixture_bytes("fruga_kw46.pdf"), REF)
    assert [(d.date, [(i.name, i.price) for i in d.items]) for d in pdf] == [
        (d.date, [(i.name, i.price) for i in d.items]) for d in table
    ]


def test_find_pdf_url(fixture_text):
    url = fruga.find_pdf_url(fixture_text("fruga.html"), REF)
    assert url.endswith("Fruga_Vital_Speiseplan_09112026.pdf")
