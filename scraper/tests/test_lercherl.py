from scraper.restaurants import lercherl

from .conftest import REF


def test_parse_week(fixture_text):
    menu = lercherl.parse(fixture_text("lercherl.html"), REF)
    assert [d.date for d in menu.days] == [f"2026-11-{n:02d}" for n in range(9, 14)]
    mon = menu.days[0]
    assert [i.name for i in mon.items] == ["Schinkenfleckerl mit Blattsalat", "Linsen mit Serviettenknödel"]
    assert all(i.price == 9.9 for i in mon.items)
    # "Tagessuppe" steht einmal als Unterzeile, nicht bei jedem Gericht
    assert mon.items[0].description is None
    assert menu.subtitle == "Alle Menüs mit Tagessuppe"


def test_inline_price_and_friday_special(fixture_text):
    menu = lercherl.parse(fixture_text("lercherl.html"), REF)
    fri = menu.days[-1].items
    assert fri[0].name == "Gebackenes Buntbarschfilet mit Erdäpfelsalat"
    assert fri[0].price == 10.9
    assert fri[-1].label == "Freitags-Spezial"
    assert fri[-1].price == 12.9


def test_notes(fixture_text):
    notes = " | ".join(lercherl.parse(fixture_text("lercherl.html"), REF).notes)
    assert "Wiener Schnitzel" in notes
    assert "9,90" in notes


def test_specific_soup_is_kept_per_item(fixture_text):
    html = fixture_text("lercherl.html").replace(
        '<p class="suppe" data-cms="w-1-s" data-cms-spalte="Suppe">Tagessuppe</p>',
        '<p class="suppe" data-cms="w-1-s" data-cms-spalte="Suppe">Frittatensuppe</p>')
    mon = lercherl.parse(html, REF).days[0]
    assert mon.items[0].description == "mit Frittatensuppe"
