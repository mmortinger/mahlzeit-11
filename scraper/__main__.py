"""Runner: `python -m scraper [--output PFAD] [--only ID ...]`.

Jeder Scraper läuft isoliert. Schlägt einer fehl, werden die letzten erfolgreichen
Daten dieses Restaurants aus der alten menu.json übernommen (stale=true, error gesetzt).
Die Datei wird nur neu geschrieben, wenn sich der Inhalt (ohne Zeitstempel) geändert hat.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from .common import iso_now, monday_of, today_vienna
from .models import SCHEMA_VERSION, RestaurantMenu

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "site" / "data" / "menu.json"
log = logging.getLogger("scraper")

# Restaurants, die nur den aktuellen Tag online haben: bereits gesehene Tage der
# laufenden Woche behalten, damit man in den Tages-Tabs zurückblättern kann.
KEEP_PAST_DAYS = {"osfizio"}


def load_old(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {r["id"]: r for r in data.get("restaurants", [])}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Alte menu.json nicht lesbar (%s) – starte ohne Altdaten", exc)
        return {}


def _merge_past_days(new: dict, old: dict | None) -> None:
    if not old:
        return
    week_start = monday_of(today_vienna()).isoformat()
    have = {d["date"] for d in new["days"]}
    kept = [d for d in old.get("days", []) if d["date"] >= week_start and d["date"] not in have]
    if kept:
        new["days"] = sorted(new["days"] + kept, key=lambda d: d["date"])


def run_one(module: Any, old: dict | None, scrape: Callable[[], RestaurantMenu] | None = None) -> dict:
    """Ein Restaurant scrapen; bei Fehler Altdaten als stale zurückgeben."""
    scrape = scrape or module.scrape
    try:
        menu = scrape()
        if not menu.days and not menu.flyer_url:
            raise ValueError("Keine Menüdaten gefunden – Seitenstruktur geändert?")
        menu.fetched_at = iso_now()
        menu.stale = False
        menu.error = None
        result = menu.to_dict()
        if module.ID in KEEP_PAST_DAYS:
            _merge_past_days(result, old)
        return result
    except Exception as exc:  # noqa: BLE001 – Isolation ist hier der Zweck
        msg = f"{type(exc).__name__}: {exc}"
        log.error("%s fehlgeschlagen: %s", module.ID, msg)
        if old:
            result = copy.deepcopy(old)
        else:
            result = RestaurantMenu(id=module.ID, name=module.NAME, source_url=module.URL).to_dict()
        result["stale"] = True
        result["error"] = msg
        return result


def _strip_volatile(data: dict) -> dict:
    data = copy.deepcopy(data)
    data.pop("generated_at", None)
    for r in data.get("restaurants", []):
        r.pop("fetched_at", None)
    return data


def build(modules: Iterable[Any], old_by_id: dict[str, dict]) -> dict:
    restaurants = [run_one(m, old_by_id.get(m.ID)) for m in modules]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_now(),
        "timezone": "Europe/Vienna",
        "restaurants": restaurants,
    }


def write_if_changed(path: Path, data: dict) -> bool:
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = None
    if old is not None and _strip_volatile(old) == _strip_volatile(data):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return True


def main(argv: list[str] | None = None) -> int:
    from .restaurants import RESTAURANTS

    parser = argparse.ArgumentParser(prog="python -m scraper", description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--only", nargs="*", help="nur diese Restaurant-IDs scrapen")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("pdfminer", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    old_by_id = load_old(args.output)
    modules = [m for m in RESTAURANTS if not args.only or m.ID in args.only]
    data = build(modules, old_by_id)

    if args.only:  # nicht ausgewählte Restaurants unverändert übernehmen
        fresh = {r["id"]: r for r in data["restaurants"]}
        data["restaurants"] = [fresh.get(m.ID) or old_by_id[m.ID]
                               for m in RESTAURANTS if m.ID in fresh or m.ID in old_by_id]

    for r in data["restaurants"]:
        n_items = sum(len(d["items"]) for d in r["days"])
        state = "STALE" if r["stale"] else "ok"
        log.info("%-10s %-5s %d Tage, %d Gerichte%s", r["id"], state, len(r["days"]), n_items,
                 f" – {r['error']}" if r["error"] else "")

    changed = write_if_changed(args.output, data)
    log.info("%s %s", "Geschrieben:" if changed else "Unverändert:", args.output)

    ok = sum(1 for r in data["restaurants"] if not r["stale"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
