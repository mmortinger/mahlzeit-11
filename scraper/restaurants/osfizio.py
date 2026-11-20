"""Osfizio – nur das Tagesmenü (zwei Menüs) in Elementor-Tabs."""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..common import (
    clean, fetch_text, parse_german_date, parse_price, split_allergens_in_parens, today_vienna,
)
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


def _split_dish(fragments: list[str]) -> tuple[str, str | None]:
    """Ein Gericht kann über mehrere Zeilen gehen -> Name ', '-verbunden, Allergene vereinigt."""
    names: list[str] = []
    codes: list[str] = []
    for frag in fragments:
        name, allergens = split_allergens_in_parens(frag)
        if name:
            names.append(name)
        if allergens:
            codes += [c for c in allergens.split(", ") if c not in codes]
    return clean(", ".join(names)), ", ".join(codes) or None


def _parse_block(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """Zeilen eines Datumsblocks -> (Vorspeise, Hauptgericht, Allergene des Hauptgerichts).
    Zeilen mit führendem Strich beginnen ein neues Gericht, andere setzen das vorige fort."""
    dishes: list[list[str]] = []
    for line in lines:
        if _LEADING_DASH.match(line) or not dishes:
            dishes.append([_LEADING_DASH.sub("", line)])
        else:
            dishes[-1].append(line)
    if not dishes:
        return None, None, None
    main, allergens = _split_dish(dishes[-1])
    starters = []
    for dish in dishes[:-1]:
        name, codes = _split_dish(dish)
        starters.append(name + (f" ({codes})" if codes else ""))
    return " / ".join(starters) or None, main or None, allergens


def _parse_lines(lines: list[str], ref: date | None) -> list[tuple[date, str | None, str, str | None]]:
    """Tab-Inhalt -> [(Datum, Vorspeise, Hauptgericht, Allergene)], ein Eintrag pro Datumsblock.
    Osfizio lässt manchmal das Menü vom Vortag unter dem aktuellen stehen: Blöcke vor heute
    werden verworfen, außer es gibt keinen anderen (dann nur der neueste)."""
    blocks: list[tuple[date, list[str]]] = []
    for line in lines:
        line = clean(line)
        if not line:
            continue
        if _DATE_ONLY.match(line):
            d = parse_german_date(line, ref)
            if d:
                blocks.append((d, []))
                continue
        if blocks:  # Text vor dem ersten Datum ignorieren
            blocks[-1][1].append(line)
    parsed = []
    for d, block_lines in blocks:
        starter, main, allergens = _parse_block(block_lines)
        if main:
            parsed.append((d, starter, main, allergens))
    today = ref or today_vienna()
    current = [b for b in parsed if b[0] >= today]
    return current or sorted(parsed, key=lambda b: b[0])[-1:]


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
        lines = [p.get_text(" ") for p in content.find_all("p")] or content.get_text("\n").splitlines()
        for d, starter, main, allergens in _parse_lines(lines, ref):
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
    normal_page = len(html) > 30_000 and any(
        h.get_text(strip=True).startswith("Mittagsmen") for h in soup.select(".elementor-heading-title"))
    if (not menu.days and normal_page and not soup.select(".elementor-tab-desktop-title")
            and not _MENU_PRICE.search(html)):
        # Seite ist normal da, aber der Menüblock wurde entfernt (so am 20.11.2026) –
        # Osfizio hat schlicht kein Menü online. Kein Parser-Fehler.
        menu.notice = "Derzeit ist auf der Website von Osfizio kein Mittagsmenü veröffentlicht."

    sub = "Mit Vorspeise (Salat oder Suppe)"
    hours = soup.find(string=_HOURS)
    if hours:
        m = _HOURS.search(hours)
        sub += f" · Mo–Fr {m.group(1).replace('.', ':')}–{m.group(2).replace('.', ':')} Uhr"
    menu.subtitle = sub
    menu.empty_hint = "Osfizio stellt nur das Tagesmenü online – oft erst am Vormittag, manchmal schon am Vorabend."
    return menu


_MENU_PRICE = re.compile(r"Mittagsmen\S*\s*€\s*\d+,\d{2}")
_HOURS = re.compile(r"(\d{1,2}[.:]\d{2})\s*-\s*(\d{1,2}[.:]\d{2})")


_OG_BLOCK = re.compile(
    r"(\d)-Mittagsmen\S*\s*€\s*(\d+,\d{2})\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+(.*?)(?=\d-Mittagsmen|Haben Sie|$)",
    re.S,
)


def _parse_og(text: str, ref: date | None, by_date: dict[str, Day]) -> None:
    for num, price, dstr, body in _OG_BLOCK.findall(text):
        parts = [p for p in re.split(r"\s+[\-–]\s*|^\s*[\-–]\s*", body) if clean(p)]
        # die og-Teile sind schon an den Strichen getrennt -> jeder Teil ein eigenes Gericht
        for d, starter, main, allergens in _parse_lines([dstr, *(f"- {x}" for x in parts)], ref):
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
    html = fetch_text(URL)
    menu = parse(html)
    if not menu.days and not menu.notice:
        soup = BeautifulSoup(html, "html.parser")
        title = clean(soup.title.get_text()) if soup.title else "-"
        tabs = len(soup.select(".elementor-tab-desktop-title"))
        raise ValueError(f"Kein Tagesmenü gefunden ({tabs} Tabs, {len(html)} Zeichen, Titel: {title!r})")
    return menu
