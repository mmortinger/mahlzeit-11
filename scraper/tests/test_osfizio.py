from scraper.restaurants import osfizio

from .conftest import REF


def test_parse_today(fixture_text):
    menu = osfizio.parse(fixture_text("osfizio.html"), REF)
    assert [d.date for d in menu.days] == ["2026-11-12"]
    m1, m2 = menu.days[0].items
    assert (m1.label, m1.price, m1.allergens) == ("Menü 1", 11.9, "A, G")
    assert m1.name.startswith("Sfiziotta (Römische Pinsa)")
    assert m1.description == "Vorspeise: Gemischter Salat"
    assert (m2.label, m2.price) == ("Menü 2", 10.9)
    assert m2.name == "Pasta mit Thunfisch-Eier-Creme, getrockneten Tomaten"
    assert m2.allergens == "A, C, D, L, O"
    assert m2.description == "Vorspeise: Gemüsecremesuppe (L)"
    assert menu.subtitle == "Mit Vorspeise (Salat oder Suppe) · Mo–Fr 11:30–15:00 Uhr"
    assert "Vormittag" in menu.empty_hint


def test_og_description_fallback(fixture_text):
    html = fixture_text("osfizio.html").replace("elementor-tab-desktop-title", "x-removed")
    menu = osfizio.parse(html, REF)
    assert [d.date for d in menu.days] == ["2026-11-12"]
    names = [i.name for i in menu.days[0].items]
    assert names[0].startswith("Sfiziotta")
    assert names[1].startswith("Pasta mit Thunfisch")
