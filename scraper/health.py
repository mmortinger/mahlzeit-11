"""Plausibilitätsprüfung nach dem Crawl – Grundlage für den Alarm im Workflow.

Fehler   : Scraper ist fehlgeschlagen (stale) – es werden Altdaten angezeigt.
Warnung  : Scraper lief, aber etwas stimmt nicht – z. B. an einem Werktag ab 11 Uhr
           kein Menü für heute (Seite nicht aktualisiert oder Parser findet nichts mehr),
           oder Interspar nur als Flugblatt-Link statt geparster Gerichte.
Feiertage und Wochenenden lösen keine Warnung aus.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

# Ab dieser Uhrzeit (Wien) muss jedes Restaurant ein Menü für heute haben.
# Der späte Cron-Lauf (10:15 UTC = 11:15/12:15 Wien) liegt danach, die frühen davor –
# so gibt es keinen Fehlalarm, wenn eine Seite erst am Vormittag aktualisiert wird.
EXPECT_TODAY_FROM = time(11, 0)


@dataclass
class Problem:
    level: str  # "Fehler" | "Warnung"
    restaurant: str
    message: str

    def __str__(self) -> str:
        return f"{self.level} – {self.restaurant}: {self.message}"


def _easter(year: int) -> date:
    """Ostersonntag (gregorianisch, Algorithmus nach Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def austrian_holidays(year: int) -> set[date]:
    easter = _easter(year)
    # gesetzliche Feiertage + 24./31.12. (keine Feiertage, aber viele Lokale haben zu bzw. kein Menü)
    fixed = [(1, 1), (1, 6), (5, 1), (8, 15), (10, 26), (11, 1), (12, 8), (12, 24), (12, 25), (12, 26), (12, 31)]
    movable = [1, 39, 50, 60]  # Ostermontag, Christi Himmelfahrt, Pfingstmontag, Fronleichnam
    return {date(year, m, d) for m, d in fixed} | {easter + timedelta(days=n) for n in movable}


def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d not in austrian_holidays(d.year)


def check(data: dict, now: datetime) -> list[Problem]:
    """`now` muss Wiener Ortszeit sein."""
    problems: list[Problem] = []
    today = now.date().isoformat()
    expect_today = is_workday(now.date()) and now.time() >= EXPECT_TODAY_FROM

    for r in data.get("restaurants", []):
        name = r.get("name") or r.get("id", "?")
        if r.get("stale") or r.get("error"):
            problems.append(Problem("Fehler", name, f"Abruf fehlgeschlagen ({r.get('error') or 'unbekannt'}) "
                                                     "– die Seite zeigt ältere Daten"))
            continue
        days = r.get("days") or []
        if not days and r.get("flyer_url"):
            problems.append(Problem("Warnung", name, "Menü konnte nicht gelesen werden – nur Flugblatt-Link"))
            continue
        has_today = any(d.get("date") == today and d.get("items") for d in days)
        # Quelle hat schon auf die Folgewoche umgestellt (Lercherl: Fr-Nachmittag) – kein Fehler
        switched = any(d.get("date", "") > today and d.get("items") for d in days)
        if expect_today and not has_today and not switched:
            problems.append(Problem("Warnung", name, f"kein Menü für heute ({today}) gefunden"))
    return problems


def markdown(problems: list[Problem]) -> str:
    if not problems:
        return "### ✅ Alle Restaurants ok\n"
    lines = ["### ⚠️ Probleme beim Crawlen", ""]
    lines += [f"- **{p.level}** – {p.restaurant}: {p.message}" for p in problems]
    return "\n".join(lines) + "\n"
