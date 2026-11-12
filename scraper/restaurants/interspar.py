"""Interspar-Restaurant – Wochen-Menüplan als iPaper-Flugblatt.

Ablauf pro Kalenderwoche:
  1. Flugblatt-URL aus der ISO-KW bauen (menuplan-kw{N}, sonst kw{NN}).
  2. PDF über '{flugblatt}/GetPDF.ashx' (GET, Redirect auf signierte CDN-URL) laden
     und per pdfplumber anhand der Wortpositionen parsen (2 Spalten x Mo–Sa).
  3. Fallback: 'pageTexts' aus der iPaper-Konfiguration im HTML.
  4. Letzter Fallback: keine Tage, nur Link + og:image als Vorschau.
Die Übersichtsseite interspar.at/gastronomie/restaurant-menueplan sitzt hinter einer
Cloudflare-JS-Challenge (403) und taugt deshalb nicht als automatischer Fallback.
"""
from __future__ import annotations

import io
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from ..common import (
    WEEKDAYS,
    clean,
    decode_html,
    fetch,
    join_hyphenated,
    normalize_allergens,
    parse_german_date,
    parse_price,
    today_vienna,
)
from ..models import Day, Item, RestaurantMenu

log = logging.getLogger(__name__)

ID = "interspar"
NAME = "Interspar"
OVERVIEW_URL = "https://www.interspar.at/gastronomie/restaurant-menueplan"
URL = OVERVIEW_URL
FLIPBOOK_URL = "https://flugblatt.interspar.at/menuplane/menuplan-kw{kw}/"

COLUMNS = ("Klassisch", "Vegetarisch")
_DAY_LABELS = ("MO", "DI", "MI", "DO", "FR", "SA")
_PRICE_TOKEN = re.compile(r"^\d{1,3},\d{2}$")
_ALLERGEN_TOKEN = re.compile(r"^[A-R],?$")
_TAG_WORDS = {"vegan"}


class ParseError(ValueError):
    pass


# --------------------------------------------------------------- Flugblatt finden

def flipbook_candidates(kw: int) -> list[str]:
    variants = dict.fromkeys([str(kw), f"{kw:02d}"])  # Reihenfolge, ohne Duplikate
    return [FLIPBOOK_URL.format(kw=v) for v in variants]


def find_flipbook(kw: int) -> tuple[str, str] | None:
    """-> (url, html) oder None, wenn für diese KW (noch/nicht mehr) kein Flugblatt existiert."""
    for url in flipbook_candidates(kw):
        try:
            resp = fetch(url)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                continue
            raise
        return url, decode_html(resp.content, resp.headers.get("Content-Type", ""))
    return None


# --------------------------------------------------------------- HTML-Metadaten

def page_meta(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def og(prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": f"og:{prop}"})
        return tag.get("content") if tag else None

    texts: list[str] = []
    m = re.search(r'"pageTexts"\s*:\s*(\[.*?\])\s*,\s*"', html, re.S)
    if m:
        try:
            texts = json.loads(m.group(1))
        except json.JSONDecodeError:
            texts = []
    return {
        "title": og("title") or (soup.title.string if soup.title else None),
        "image": og("image"),
        "url": og("url"),
        "page_texts": texts,
    }


def week_monday(title: str | None, fallback: date) -> date:
    """'Mo., 09.11.26 – Sa., 14.11.26' -> date(2026, 11, 9)."""
    if title:
        d = parse_german_date(title, fallback)
        if d:
            return d - timedelta(days=d.weekday())
    return fallback


# --------------------------------------------------------------- PDF-Parser

def parse_pdf(data: bytes, monday: date) -> list[Day]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            raise ParseError("PDF ohne Seiten")
        page = pdf.pages[0]
        words = page.extract_words(extra_attrs=["size"])
        mid = page.width / 2

    if not words:
        raise ParseError("PDF enthält keinen Text (nur Bild?)")

    labels = [w for w in words if w["text"] in _DAY_LABELS and w["x0"] < 30]
    if len(labels) < 5:
        raise ParseError(f"Tageslabels nicht gefunden ({len(labels)})")
    header = next((w for w in words if w["text"].upper() == "KLASSISCH"), None)
    top_min = header["bottom"] + 5 if header else min(l["top"] for l in labels) - 40
    legend = next((w for w in words if w["text"].startswith("Glutenhaltig")), None)
    top_max = legend["top"] - 3 if legend else max(l["bottom"] for l in labels) + 60

    def row_of(w) -> str:
        center = (w["top"] + w["bottom"]) / 2
        nearest = min(labels, key=lambda l: abs((l["top"] + l["bottom"]) / 2 - center))
        return nearest["text"]

    cells: dict[tuple[str, int], list[dict]] = defaultdict(list)
    prices: dict[tuple[str, int], float] = {}
    for w in words:
        if w in labels or w["x0"] < 30 or not (top_min <= w["top"] <= top_max):
            continue
        key = (row_of(w), 0 if w["x0"] < mid else 1)
        if _PRICE_TOKEN.match(w["text"]):
            prices[key] = parse_price(w["text"])
        else:
            cells[key].append(w)

    col_default = {
        col: Counter(p for (r, c), p in prices.items() if c == col).most_common(1)[0][0]
        if any(c == col for (_, c) in prices) else None
        for col in (0, 1)
    }

    days: dict[str, Day] = {}
    for label in _DAY_LABELS:
        for col in (0, 1):
            ws = cells.get((label, col))
            if not ws:
                continue
            item = _cell_to_item(ws, col)
            item.price = prices.get((label, col), col_default[col])
            d = monday + timedelta(days=WEEKDAYS[label.lower()])
            days.setdefault(label, Day(date=d.isoformat())).items.append(item)

    _validate(days)
    return [days[l] for l in _DAY_LABELS if l in days]


def _cell_to_item(ws: list[dict], col: int) -> Item:
    ws = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
    tags: list[str] = []
    allergens: list[str] = []
    text_words: list[str] = []
    for w in ws:
        t = w["text"]
        if t.lower() in _TAG_WORDS:
            tags.append(t.lower())
        elif _ALLERGEN_TOKEN.match(t) and w["size"] < 8:
            allergens.append(t)
        else:
            text_words.append(t)
    return _make_item(" ".join(text_words), " ".join(allergens), col, tags)


def _make_item(text: str, allergens: str, col: int, tags: list[str]) -> Item:
    vegetarian = True if (col == 1 or "vegan" in tags) else None
    return Item(
        label=COLUMNS[col],
        name=join_hyphenated(clean(text)),
        allergens=normalize_allergens(allergens),
        vegetarian=vegetarian,
        tags=tags,
    )


def _validate(days: dict[str, Day]) -> None:
    for label in _DAY_LABELS[:5]:
        day = days.get(label)
        if not day or len(day.items) != 2 or not all(i.name for i in day.items):
            raise ParseError(f"Unplausibles Ergebnis für {label}")


# --------------------------------------------------------------- pageTexts-Fallback

_SEGMENT = re.compile(
    r"(?P<text>.+?)\s(?P<all>[A-R](?:\s*,\s*[A-R])*)(?=\s|$)"
    r"(?P<post>(?:\s+(?:vegan|\d{1,3},\d{2}))*)"
)


def parse_page_text(text: str, monday: date) -> list[Day]:
    """Fließtext der iPaper-Seite. Reihenfolge: Klassisch Mo–Fr, Vegetarisch Mo–Fr,
    dann Samstag Klassisch + Vegetarisch. Weniger robust als das PDF (die Wortreihenfolge
    ist teils verdreht), deshalb nur Fallback."""
    text = clean(text)
    start = re.search(r"\bMO\s+DI\s+MI\s+DO\s+FR\b", text)
    end = text.find(" A Glutenhaltiges")
    if not start or end < 0:
        raise ParseError("pageTexts: Struktur nicht erkannt")
    body = text[start.end(): end]
    body = re.sub(r"\b(?:MO|DI|MI|DO|FR|SA)\b", " ", body)
    body = clean(body)

    segments = []
    for m in _SEGMENT.finditer(body):
        post = m.group("post") or ""
        segments.append(
            {
                "text": m.group("text"),
                "allergens": m.group("all"),
                "tags": ["vegan"] if "vegan" in post else [],
                "price": parse_price(post),
            }
        )
    if len(segments) not in (10, 12):
        raise ParseError(f"pageTexts: {len(segments)} statt 10/12 Gerichten")

    def col_price(rng: range) -> float | None:
        return next((segments[i]["price"] for i in rng if segments[i]["price"]), None)

    defaults = {0: col_price(range(0, 5)), 1: col_price(range(5, 10))}
    layout = [(i, 0, i) for i in range(5)] + [(i, 1, i + 5) for i in range(5)]
    if len(segments) == 12:
        layout += [(5, 0, 10), (5, 1, 11)]

    days: dict[str, Day] = {}
    for wd, col, idx in layout:
        seg = segments[idx]
        item = _make_item(seg["text"], seg["allergens"], col, seg["tags"])
        item.price = seg["price"] or defaults[col]
        label = _DAY_LABELS[wd]
        d = monday + timedelta(days=wd)
        days.setdefault(label, Day(date=d.isoformat())).items.append(item)
    for day in days.values():
        day.items.sort(key=lambda i: COLUMNS.index(i.label))
    _validate(days)
    return [days[l] for l in _DAY_LABELS if l in days]


# --------------------------------------------------------------- Woche komplett

def parse_week(url: str, html: str, pdf_bytes: bytes | None, iso_monday: date) -> tuple[list[Day], dict, str]:
    """-> (Tage, Metadaten, verwendete Methode)"""
    meta = page_meta(html)
    monday = week_monday(meta["title"], iso_monday)
    if pdf_bytes:
        try:
            return parse_pdf(pdf_bytes, monday), meta, "pdf"
        except Exception as exc:  # noqa: BLE001 – bewusst breit, Fallback folgt
            log.warning("Interspar PDF-Parser fehlgeschlagen (%s): %s", url, exc)
    for txt in meta["page_texts"]:
        try:
            return parse_page_text(txt, monday), meta, "pagetext"
        except Exception as exc:  # noqa: BLE001
            log.warning("Interspar pageTexts-Parser fehlgeschlagen (%s): %s", url, exc)
    return [], meta, "none"


def _download_pdf(url: str) -> bytes | None:
    try:
        resp = fetch(url.rstrip("/") + "/GetPDF.ashx")
    except requests.RequestException as exc:
        log.warning("Interspar PDF-Download fehlgeschlagen: %s", exc)
        return None
    if not resp.content.startswith(b"%PDF"):
        log.warning("Interspar GetPDF lieferte kein PDF (%s)", resp.headers.get("Content-Type"))
        return None
    return resp.content


def scrape() -> RestaurantMenu:
    today = today_vienna()
    menu = RestaurantMenu(id=ID, name=NAME, source_url=OVERVIEW_URL)
    found_any = False
    methods = []

    # aktuelle und nächste Woche (Vorschau am Wochenende/Freitag)
    for offset in (0, 7):
        ref = today + timedelta(days=offset)
        iso_year, kw, _ = ref.isocalendar()
        iso_monday = date.fromisocalendar(iso_year, kw, 1)
        hit = find_flipbook(kw)
        if not hit:
            log.info("Interspar: kein Flugblatt für KW %s", kw)
            continue
        url, html = hit
        days, meta, method = parse_week(url, html, _download_pdf(url), iso_monday)
        # Sicherheitscheck: Flugblatt muss zur angefragten Woche gehören
        if days and date.fromisoformat(days[0].date) - timedelta(days=date.fromisoformat(days[0].date).weekday()) != iso_monday:
            log.warning("Interspar KW %s: Flugblatt gehört zu anderer Woche – ignoriert", kw)
            continue
        found_any = True
        methods.append(f"KW{kw}: {method}")
        menu.days.extend(days)
        if offset == 0 or not menu.flyer_url:
            menu.flyer_url = url
            menu.preview_image = meta["image"]
            menu.source_url = url
            if days:
                menu.valid_from, menu.valid_to = days[0].date, days[-1].date

    if not found_any:
        raise RuntimeError("Kein Interspar-Flugblatt für diese oder nächste KW gefunden")

    menu.notes = [
        "Mittagsmenü mit Suppe oder Menüsalat",
        "Täglich 10:30–16:00 Uhr, solange der Vorrat reicht",
    ]
    log.info("Interspar Quellen: %s", ", ".join(methods))
    return menu
