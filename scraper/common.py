"""Gemeinsame Helfer: HTTP, Preise, deutsche Datumsangaben, Zeitzone."""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

VIENNA = ZoneInfo("Europe/Vienna")
USER_AGENT = (
    "MAhlzeit11-MenuBot/1.0 (+Mittagsmenue-Aggregator; 3 Abrufe pro Werktag)"
)
TIMEOUT = 20  # Sekunden

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "de-AT,de;q=0.9",
            }
        )
        _session = s
    return _session


def fetch(url: str, *, retries: int = 1, **kwargs) -> requests.Response:
    """GET mit Timeout und einem sanften Retry (nicht bei 4xx)."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = session().get(url, timeout=TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code < 500:
                raise  # 4xx: Wiederholen bringt nichts
            last_exc = exc
        except requests.RequestException as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(3)
    assert last_exc is not None
    raise last_exc


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([\w-]+)""", re.I)


def decode_html(content: bytes, header_content_type: str = "") -> str:
    """HTML-Bytes dekodieren: charset aus Header, sonst aus <meta>, sonst UTF-8."""
    m = re.search(r"charset=([\w-]+)", header_content_type or "", re.I)
    encoding = m.group(1) if m else None
    if not encoding:
        mm = _META_CHARSET.search(content[:4096])
        encoding = mm.group(1).decode("ascii") if mm else "utf-8"
    return content.decode(encoding, errors="replace")


def fetch_text(url: str) -> str:
    resp = fetch(url)
    return decode_html(resp.content, resp.headers.get("Content-Type", ""))


# ---------------------------------------------------------------- Zeit

def now_vienna() -> datetime:
    return datetime.now(VIENNA)


def today_vienna() -> date:
    return now_vienna().date()


def iso_now() -> str:
    return now_vienna().isoformat(timespec="seconds")


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ---------------------------------------------------------------- Text

_WS = re.compile(r"\s+")


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("­", "")
    text = _WS.sub(" ", text).strip()
    text = re.sub(r"\s+,", ",", text)  # "Creme ,getrocknet" -> "Creme,getrocknet"
    return re.sub(r",(?=[^\s\d])", ", ", text)  # -> "Creme, getrocknet" (Preise "10,90" bleiben)


def join_hyphenated(text: str) -> str:
    """'Petersilien- kartoffeln' -> 'Petersilienkartoffeln',
    'Gemüse-Kartoffel- Auflauf' -> 'Gemüse-Kartoffel-Auflauf'."""

    def repl(m: re.Match) -> str:
        nxt = m.group(2)
        return m.group(1) + ("" if nxt.islower() else "-") + nxt

    return re.sub(r"(\w)- (\w)", repl, text)


# ---------------------------------------------------------------- Preise

_PRICE = re.compile(r"(\d{1,3})[,.](\d{2})\b")


def parse_price(text: str | None) -> float | None:
    """'€ 10,90' -> 10.9; None wenn kein Preis gefunden."""
    if not text:
        return None
    m = _PRICE.search(text)
    if not m:
        return None
    return round(int(m.group(1)) + int(m.group(2)) / 100, 2)


# ---------------------------------------------------------------- Allergene

# "A, C, G, M, L" / "A,G" / "A, C, D,L,O"
ALLERGEN_GROUP = r"[A-R](?:\s*,\s*[A-R])*"
_ALLERGEN_PARENS = re.compile(r"\(\s*(" + ALLERGEN_GROUP + r")\s*\)")


def normalize_allergens(codes: str | None) -> str | None:
    if not codes:
        return None
    letters = re.findall(r"[A-R]", codes)
    return ", ".join(letters) if letters else None


def split_allergens_in_parens(text: str) -> tuple[str, str | None]:
    """'Pasta mit X (A, C, D,L,O)' -> ('Pasta mit X', 'A, C, D, L, O')."""
    found = _ALLERGEN_PARENS.findall(text)
    if not found:
        return clean(text), None
    stripped = clean(_ALLERGEN_PARENS.sub("", text))
    return stripped, normalize_allergens(",".join(found))


# ---------------------------------------------------------------- Datum

MONTHS = {
    "jänner": 1, "januar": 1, "jan": 1,
    "februar": 2, "feber": 2, "feb": 2,
    "märz": 3, "maerz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

WEEKDAYS = {
    "montag": 0, "mo": 0,
    "dienstag": 1, "di": 1,
    "mittwoch": 2, "mi": 2,
    "donnerstag": 3, "do": 3,
    "freitag": 4, "fr": 4,
    "samstag": 5, "sa": 5,
    "sonntag": 6, "so": 6,
}

_DATE_NUMERIC = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{4}|\d{2})\b)?")
_DATE_MONTHNAME = re.compile(
    r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\.?(?:\s+(\d{4}))?"
)


def _resolve_year(day: int, month: int, ref: date) -> date:
    """Jahr so wählen, dass das Datum möglichst nah am Referenzdatum liegt
    (z. B. 'Montag, 29.12.' im Jänner -> Vorjahr)."""
    candidates = []
    for y in (ref.year - 1, ref.year, ref.year + 1):
        try:
            candidates.append(date(y, month, day))
        except ValueError:
            pass
    if not candidates:
        raise ValueError(f"Ungültiges Datum {day}.{month}.")
    return min(candidates, key=lambda d: abs((d - ref).days))


def parse_german_date(text: str, ref: date | None = None) -> date | None:
    """Erkennt '12.11.2026', 'Montag, 9.11.', 'Mo., 09.11.26', 'Montag, 9. November 2026'.
    Fehlt das Jahr, wird es aus dem Referenzdatum (Standard: heute in Wien) abgeleitet."""
    if not text:
        return None
    ref = ref or today_vienna()
    text = clean(text)

    m = _DATE_MONTHNAME.search(text)
    if m and m.group(2).lower() in MONTHS:
        day, month = int(m.group(1)), MONTHS[m.group(2).lower()]
        if m.group(3):
            return date(int(m.group(3)), month, day)
        return _resolve_year(day, month, ref)

    m = _DATE_NUMERIC.search(text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = m.group(3)
        if year:
            y = int(year)
            if y < 100:
                y += 2000
            return date(y, month, day)
        return _resolve_year(day, month, ref)
    return None
