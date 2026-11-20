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


def test_parse_with_leftover_old_day_and_multiline_dish(fixture_text):
    # 18.11.: Tab 2 enthält unter dem heutigen Menü noch das vom 17.11.,
    # Tab 1 hat ein Hauptgericht über zwei Zeilen.
    from datetime import date
    menu = osfizio.parse(fixture_text("osfizio_2026-11-18.html"), date(2026, 11, 18))
    assert [d.date for d in menu.days] == ["2026-11-18"]
    m1, m2 = menu.days[0].items
    assert m1.name == ("Sfiziotta (Römische Pinsa) mit Tomatensauce, Mozzarella, Gemüse, "
                       "Sardellen, Oliven, Kapern")
    assert (m1.allergens, m1.description) == ("A, G", "Vorspeise: Gemischter Salat")
    assert m2.name == "Lasagna Classica (mit Mozzarella und Faschiertem)"
    assert (m2.allergens, m2.description) == ("A, C, G, L", "Vorspeise: Brokkolicremesuppe (L)")


def test_only_old_day_left_keeps_newest(fixture_text):
    from datetime import date
    menu = osfizio.parse(fixture_text("osfizio_2026-11-18.html"), date(2026, 11, 19))
    assert [d.date for d in menu.days] == ["2026-11-18"]  # nichts Neueres da -> neuester Block


def test_scrape_error_is_descriptive(monkeypatch):
    import pytest
    monkeypatch.setattr(osfizio, "fetch_text", lambda url: "<html><title>Wartung</title></html>")
    with pytest.raises(ValueError, match="0 Tabs.*Wartung"):
        osfizio.scrape()



def test_menu_block_removed_is_notice_not_error(fixture_text, monkeypatch):
    # 20.11.2026: Seite normal erreichbar, Menü-Tabs komplett entfernt
    from datetime import date
    html = fixture_text("osfizio_ohne_menue.html")
    menu = osfizio.parse(html, date(2026, 11, 20))
    assert menu.days == [] and "kein Mittagsmenü" in menu.notice
    monkeypatch.setattr(osfizio, "fetch_text", lambda url: html)
    assert osfizio.scrape().notice  # kein ValueError


def test_unparseable_tabs_are_still_an_error(fixture_text, monkeypatch):
    import pytest
    html = fixture_text("osfizio.html").replace("12.11.2026", "irgendwann")
    monkeypatch.setattr(osfizio, "fetch_text", lambda url: html)
    with pytest.raises(ValueError):
        osfizio.scrape()
