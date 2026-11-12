"""Lercherl von Hernals – Wochenmenü als HTML (ein <article class="tag"> pro Tag)."""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..common import clean, fetch_text, parse_german_date, parse_price
from ..models import Day, Item, RestaurantMenu

ID = "lercherl"
NAME = "Lercherl"
URL = "https://www.lercherl.at/wochenmenue.html"

DEFAULT_PRICE = 9.90
_INLINE_PRICE = re.compile(r"\(\s*€\s*\d{1,3}[,.]\d{2}\s*\)")


def _split_inline_price(text: str, default: float | None) -> tuple[str, float | None]:
    m = _INLINE_PRICE.search(text)
    if not m:
        return clean(text), default
    return clean(_INLINE_PRICE.sub("", text)), parse_price(m.group(0))


def parse(html: str, ref: date | None = None) -> RestaurantMenu:
    soup = BeautifulSoup(html, "html.parser")
    menu = RestaurantMenu(id=ID, name=NAME, source_url=URL)

    lead = soup.select_one("p.lead")
    lead_text = clean(lead.get_text(" ")) if lead else ""
    default_price = parse_price(lead_text) or DEFAULT_PRICE
    if lead_text:
        menu.notes.append(lead_text.rstrip("."))

    spezial = soup.select_one("aside.spezial-karte h2, #spz-titel")
    if spezial:
        menu.notes.append(f"Täglich als Alternative: {clean(spezial.get_text(' '))}")

    days: list[Day] = []
    for art in soup.select("article.tag"):
        h3 = art.find("h3")
        title = clean(h3.get_text(" ")) if h3 else ""

        if "tag--spezial" in (art.get("class") or []):
            # Freitags-Spezial: hängt am Freitag der Woche
            texts = [clean(p.get_text(" ")) for p in art.find_all("p")]
            price = next((parse_price(t) for t in texts if parse_price(t)), None)
            name = next((t for t in texts if not parse_price(t)), "")
            if name:
                friday = next((d for d in days if date.fromisoformat(d.date).weekday() == 4), None)
                item = Item(label=title or "Freitags-Spezial", name=name, price=price)
                if friday:
                    friday.items.append(item)
                else:
                    menu.notes.append(f"{title}: {name}" + (f" (€ {price:.2f})".replace(".", ",") if price else ""))
            continue

        d = parse_german_date(title, ref)
        if not d:
            continue
        soup_p = art.select_one('[data-cms-spalte="Suppe"], p.suppe')
        soup_name = clean(soup_p.get_text(" ")) if soup_p else None

        dishes = art.select('[data-cms-spalte^="Gericht"]')
        if not dishes:  # Fallback ohne CMS-Attribute
            dishes = [p for p in art.find_all("p") if "suppe" not in (p.get("class") or [])]

        items = []
        for i, p in enumerate(dishes, start=1):
            text = clean(p.get_text(" "))
            if not text:
                continue
            name, price = _split_inline_price(text, default_price)
            items.append(
                Item(
                    label=f"Menü {i}",
                    name=name,
                    price=price,
                    description=f"mit {soup_name}" if soup_name else None,
                )
            )
        days.append(Day(date=d.isoformat(), items=items))

    menu.days = sorted(days, key=lambda x: x.date)
    hint = soup.find(string=re.compile("Allergen", re.I))
    if hint:
        menu.notes.append(clean(hint))
    return menu


def scrape() -> RestaurantMenu:
    return parse(fetch_text(URL))
