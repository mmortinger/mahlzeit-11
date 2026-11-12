"""Fruga Vital – HTML-Tabelle „Aktueller Speiseplan“, Wochen-PDF als Fallback."""
from __future__ import annotations

import io
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from ..common import clean, fetch, fetch_text, monday_of, parse_german_date, parse_price, today_vienna
from ..models import Day, Item, RestaurantMenu

ID = "fruga"
NAME = "Fruga Vital"
URL = "https://frugavital.at/"

_DAY_HEADER = re.compile(
    r"^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s+\d{1,2}\.\s*\d{1,2}\.", re.I
)
_PRICE_ONLY = re.compile(r"^(€\s*)?\d{1,3},\d{2}$")
_PDF_LINK = re.compile(r"Fruga_Vital_Speiseplan_(\d{2})(\d{2})(\d{4})\.pdf", re.I)
_OUTSIDE = re.compile(r"Außerhalb des Menüplans[^.]*\.", re.I)


def _keep(d: date, ref: date) -> bool:
    """Nur aktuelle Woche ab Montag (der Vor-Samstag in der Tabelle fliegt raus)."""
    return d >= monday_of(ref)


def _make_items(dishes: list[tuple[str, float | None]]) -> list[Item]:
    return [Item(label=f"Gericht {i}", name=n, price=p) for i, (n, p) in enumerate(dishes, start=1)]


def parse(html: str, ref: date | None = None) -> RestaurantMenu:
    ref = ref or today_vienna()
    soup = BeautifulSoup(html, "html.parser")
    menu = RestaurantMenu(id=ID, name=NAME, source_url=URL)

    table = soup.select_one("table.menuetabelle") or soup.find("table")
    days: list[Day] = []
    if table:
        current: date | None = None
        dishes: list[tuple[str, float | None]] = []

        def flush() -> None:
            if current and dishes and _keep(current, ref):
                days.append(Day(date=current.isoformat(), items=_make_items(dishes)))

        for tr in table.find_all("tr"):
            cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if not cells:
                continue
            if _DAY_HEADER.match(cells[0]):
                flush()
                current, dishes = parse_german_date(cells[0], ref), []
                continue
            if current is None:
                continue
            name = cells[0]
            price = parse_price(cells[1]) if len(cells) > 1 else None
            dishes.append((name, price))
        flush()
    menu.days = sorted(days, key=lambda x: x.date)

    page_text = clean(soup.get_text(" "))
    m = _OUTSIDE.search(page_text)
    always = _ALWAYS.search(m.group(0)) if m else None
    if always:
        menu.subtitle = f"Immer zu haben: {always.group(1)}"
    elif m:
        menu.notes.append(m.group(0))
    return menu


# "... bieten wir immer frisch gebackene Surschnitzel, Hühnerschnitzel und Kabeljaufilet an."
_ALWAYS = re.compile(r"immer\s+(?:frisch\s+)?(?:gebackene\s+)?(.+?)\s+an\.", re.I)


def find_pdf_url(html: str, ref: date) -> str | None:
    """Link auf das Wochen-PDF, dessen Startdatum in der Woche von ref liegt."""
    soup = BeautifulSoup(html, "html.parser")
    monday = monday_of(ref)
    for a in soup.find_all("a", href=True):
        m = _PDF_LINK.search(a["href"])
        if not m:
            continue
        start = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if monday <= start <= monday + timedelta(days=6) or monday_of(start) == monday:
            return a["href"]
    return None


_PDF_DISH = re.compile(r"^(.*\S)\s+(\d{1,3},\d{2})$")
_PDF_END = re.compile(r"Bestellung|Mitnehm", re.I)


def parse_pdf(data: bytes, ref: date | None = None) -> list[Day]:
    """PDF-Text (pdfplumber): Tageskopf, danach je Zeile 'Gericht 12,90'."""
    import pdfplumber

    ref = ref or today_vienna()
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    days: list[Day] = []
    current: date | None = None
    dishes: list[tuple[str, float | None]] = []

    def flush() -> None:
        if current and dishes and _keep(current, ref):
            days.append(Day(date=current.isoformat(), items=_make_items(dishes)))

    for raw in text.splitlines():
        line = clean(raw)
        if _DAY_HEADER.match(line):
            flush()
            current, dishes = parse_german_date(line, ref), []
        elif _PDF_END.search(line):
            break
        elif current is not None and line and not _PRICE_ONLY.match(line):
            m = _PDF_DISH.match(line)
            dishes.append((m.group(1), parse_price(m.group(2))) if m else (line, None))
    flush()
    return sorted(days, key=lambda x: x.date)


def scrape() -> RestaurantMenu:
    html = fetch_text(URL)
    ref = today_vienna()
    menu = parse(html, ref)
    if not menu.days:
        pdf_url = find_pdf_url(html, ref)
        if pdf_url:
            menu.days = parse_pdf(fetch(pdf_url).content, ref)
            menu.notes.append("Quelle: Wochen-PDF (HTML-Tabelle war leer)")
    return menu
