"""Osfizio – nur das Tagesmenü (zwei Menüs) in Elementor-Tabs."""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..common import clean, fetch_text, parse_german_date, parse_price, split_allergens_in_parens
from ..models import Day, Item, RestaurantMenu

ID = "osfizio"
NAME = "Osfizio"
URL = "https://www.osfizio.at/mittagsmenus/"

_LEADING_DASH = re.compile(r"^[\-–—•]\s*")
_DATE_ONLY = re.compile(r"^\d{1,2}\.\d{1,2}\.(\d{2,4})?$")
_MENU_TITLE = re.compile(r"(\d)\s*-\s*Mittagsmen", re.I)


def _label(title: str) -> str:
    m = _MENU_TITLE.search(title)
    return f"Menü {m.group(1)}" if m else re.sub(r"\s*€.*$", "", title)


def _parse_lines(lines: list[str], ref: date | None) -> tuple[date | None, str | None, str | None, str | None]:
    """-> (Datum, Vorspeise, Hauptgericht, Allergene des Hauptgerichts)"""
    the_date = None
    dishes: list[str] = []
    for line in lines:
        line = clean(line)
        if not line:
            continue
        if _DATE_ONLY.match(line):
            the_date = parse_german_date(line, ref)
            continue
        dishes.append(_LEADING_DASH.sub("", line))
    if not dishes:
        return the_date, None, None, None
    main_raw = dishes[-1]
    starter_raw = " / ".join(dishes[:-1]) or None
    main, allergens = split_allergens_in_parens(main_raw)
    starter = None
    if starter_raw:
        s_name, s_all = split_allergens_in_parens(starter_raw)
        starter = s_name + (f" ({s_all})" if s_all else "")
    return the_date, starter, main, allergens


def parse(html: str, ref: date | None = None) -> RestaurantMenu:
    soup = BeautifulSoup(html, "html.parser")
    menu = RestaurantMenu(id=ID, name=NAME, source_url=URL)
    by_date: dict[str, Day] = {}

    for title_el in soup.select(".elementor-tab-desktop-title"):
        title = clean(title_el.get_text(" "))
        content_id = title_el.get("aria-controls")
        content = soup.find(id=content_id) if content_id else None
        if not content:
            continue
        lines = [p.get_text(" ") for p in content.find_all("p")]
        d, starter, main, allergens = _parse_lines(lines, ref)
        if not d or not main:
            continue
        day = by_date.setdefault(d.isoformat(), Day(date=d.isoformat()))
        day.items.append(
            Item(
                label=_label(title),
                name=main,
                price=parse_price(title),
                allergens=allergens,
                description=f"Vorspeise: {starter}" if starter else None,
            )
        )

    if not by_date:
        # Fallback: og:description enthält den gleichen Text als Fließtext
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            _parse_og(og["content"], ref, by_date)

    menu.days = sorted(by_date.values(), key=lambda x: x.date)

    sub = "Mit Vorspeise (Salat oder Suppe)"
    hours = soup.find(string=_HOURS)
    if hours:
        m = _HOURS.search(hours)
        sub += f" · Mo–Fr {m.group(1).replace('.', ':')}–{m.group(2).replace('.', ':')} Uhr"
    menu.subtitle = sub
    menu.empty_hint = "Osfizio stellt nur das Tagesmenü online – oft erst am Vormittag, manchmal schon am Vorabend."
    return menu


_HOURS = re.compile(r"(\d{1,2}[.:]\d{2})\s*-\s*(\d{1,2}[.:]\d{2})")


_OG_BLOCK = re.compile(
    r"(\d)-Mittagsmen\S*\s*€\s*(\d+,\d{2})\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+(.*?)(?=\d-Mittagsmen|Haben Sie|$)",
    re.S,
)


def _parse_og(text: str, ref: date | None, by_date: dict[str, Day]) -> None:
    for num, price, dstr, body in _OG_BLOCK.findall(text):
        parts = [p for p in re.split(r"\s+[\-–]\s*|^\s*[\-–]\s*", body) if clean(p)]
        d, starter, main, allergens = _parse_lines([dstr, *parts], ref)
        if not d or not main:
            continue
        day = by_date.setdefault(d.isoformat(), Day(date=d.isoformat()))
        day.items.append(
            Item(
                label=f"Menü {num}",
                name=main,
                price=parse_price(price),
                allergens=allergens,
                description=f"Vorspeise: {starter}" if starter else None,
            )
        )


def scrape() -> RestaurantMenu:
    return parse(fetch_text(URL))
