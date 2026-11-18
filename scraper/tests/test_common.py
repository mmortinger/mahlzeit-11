from datetime import date

import pytest

from scraper.common import (
    clean,
    join_hyphenated,
    normalize_allergens,
    parse_german_date,
    parse_price,
    split_allergens_in_parens,
)

REF = date(2026, 11, 12)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Montag, 9. November 2026", date(2026, 11, 9)),
        ("Montag, 9.11.2026", date(2026, 11, 9)),
        ("12.11.2026", date(2026, 11, 12)),
        ("Mo., 09.11.26 – Sa., 14.11.26", date(2026, 11, 9)),
        ("Montag, 9.11.", date(2026, 11, 9)),  # ohne Jahr
        ("Freitag, 13. Nov.", date(2026, 11, 13)),
        ("kein Datum", None),
    ],
)
def test_parse_german_date(text, expected):
    assert parse_german_date(text, REF) == expected


def test_year_inferred_across_new_year():
    assert parse_german_date("Montag, 29.12.", date(2027, 1, 2)) == date(2026, 12, 29)
    assert parse_german_date("Freitag, 2.1.", date(2026, 12, 30)) == date(2027, 1, 2)


@pytest.mark.parametrize(
    "text,expected",
    [("€ 9,90", 9.9), ("(€ 10,90)", 10.9), ("12.90", 12.9), ("2-Mittagsmenü € 10,90", 10.9), ("ohne", None)],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_allergens():
    assert split_allergens_in_parens("Pasta (A, C, D,L,O)") == ("Pasta", "A, C, D, L, O")
    assert split_allergens_in_parens("Salat") == ("Salat", None)
    assert normalize_allergens("A,G") == "A, G"


def test_text_helpers():
    assert join_hyphenated("mit Petersilien- kartoffeln") == "mit Petersilienkartoffeln"
    assert join_hyphenated("Gemüse-Kartoffel- Auflauf") == "Gemüse-Kartoffel-Auflauf"
    assert clean("Creme ,getrockneten  Tomaten") == "Creme, getrockneten Tomaten"
    assert clean("€ 10,90") == "€ 10,90"


def test_allergens_new_notations():
    assert split_allergens_in_parens("Hülsenfrüchtesuppe (A/L)") == ("Hülsenfrüchtesuppe", "A, L")
    assert split_allergens_in_parens("Lasagna (mit Mozzarella und Faschiertem A,C,G,L)") == (
        "Lasagna (mit Mozzarella und Faschiertem)", "A, C, G, L")
    assert split_allergens_in_parens("Sfiziotta (Römische Pinsa) mit Gemüse (A,G)") == (
        "Sfiziotta (Römische Pinsa) mit Gemüse", "A, G")
    assert split_allergens_in_parens("Pasta (mit Ei)") == ("Pasta (mit Ei)", None)
