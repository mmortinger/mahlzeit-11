from datetime import date

import pytest

from scraper.restaurants import interspar

KW46 = date(2026, 11, 9)
KW47 = date(2026, 11, 16)


def test_flipbook_candidates():
    assert interspar.flipbook_candidates(46) == ["https://flugblatt.interspar.at/menuplane/menuplan-kw46/"]
    assert interspar.flipbook_candidates(5) == [
        "https://flugblatt.interspar.at/menuplane/menuplan-kw5/",
        "https://flugblatt.interspar.at/menuplane/menuplan-kw05/",
    ]


def test_meta(fixture_text):
    meta = interspar.page_meta(fixture_text("interspar_kw46.html"))
    assert meta["title"].startswith("Mo., 09.11.26")
    assert meta["image"].startswith("https://cdn.ipaper.io/OpenGraphImage")
    assert "Majoranfleisch" in meta["page_texts"][0]
    assert interspar.week_monday(meta["title"], date(2000, 1, 3)) == KW46


def test_pdf_kw46(fixture_bytes):
    days = interspar.parse_pdf(fixture_bytes("interspar_kw46.pdf"), KW46)
    assert [d.date for d in days] == [f"2026-11-{n:02d}" for n in range(9, 15)]
    mon_k, mon_v = days[0].items
    assert mon_k.label == "Klassisch" and mon_v.label == "Vegetarisch"
    assert mon_k.name == "Majoranfleisch von der Schweinsschulter, mit Nockerl"
    assert (mon_k.price, mon_k.allergens, mon_k.vegetarian) == (9.4, "A, C, G, M, L", None)
    assert (mon_v.price, mon_v.vegetarian) == (8.4, True)
    tue_v = days[1].items[1]
    assert tue_v.name == "Thai Curry mit Paprika, Mango und Basmatireis"
    assert tue_v.tags == ["vegan"]
    assert days[2].items[1].name == "Gemüse-Kartoffel-Auflauf mit Tzatziki"
    assert days[5].items[0].name == "1/2 Grillhendl mit Pommes"  # Samstag, "SA" nicht im Namen


def test_pdf_kw47(fixture_bytes):
    days = interspar.parse_pdf(fixture_bytes("interspar_kw47.pdf"), KW47)
    assert days[0].items[0].name == "Ćevapčići mit Pommes und Ajvar"
    assert days[5].items[0].name == "Saftgulasch von der Schweinsschulter, mit Semmelknödel und Schnittlauch"
    assert all(len(d.items) == 2 for d in days)


@pytest.mark.parametrize("kw,monday", [(46, KW46), (47, KW47)])
def test_pagetext_fallback(fixture_text, fixture_bytes, kw, monday):
    meta = interspar.page_meta(fixture_text(f"interspar_kw{kw}.html"))
    by_text = interspar.parse_page_text(meta["page_texts"][0], monday)
    by_pdf = interspar.parse_pdf(fixture_bytes(f"interspar_kw{kw}.pdf"), monday)
    assert [d.date for d in by_text] == [d.date for d in by_pdf]
    # Mo–Fr identisch; am Samstag ist die Wortreihenfolge im pageText teils verdreht
    for t, p in zip(by_text[:5], by_pdf[:5]):
        assert [(i.label, i.name, i.price, i.allergens, i.tags) for i in t.items] == [
            (i.label, i.name, i.price, i.allergens, i.tags) for i in p.items
        ]


def test_parse_week_falls_back(fixture_text):
    html = fixture_text("interspar_kw46.html")
    days, meta, method = interspar.parse_week("u", html, b"%PDF-kaputt", KW46)
    assert method == "pagetext" and len(days) == 6
    days, meta, method = interspar.parse_week("u", html.replace('"pageTexts"', '"x"'), None, KW46)
    assert method == "none" and days == [] and meta["image"]


def test_subtitle_from_text(fixture_text):
    meta = interspar.page_meta(fixture_text("interspar_kw46.html"))
    assert interspar.subtitle_from_text(meta["page_texts"][0]) == (
        "Mit Suppe oder Menüsalat · täglich 10:30–16:00 Uhr")
    assert interspar.subtitle_from_text("") == "Mit Suppe oder Menüsalat"
