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
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

from . import common, health
from .common import iso_now, monday_of, now_vienna, today_vienna
from .models import SCHEMA_VERSION, RestaurantMenu

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "site" / "data" / "menu.json"
DEFAULT_DEBUG_DIR = Path(__file__).resolve().parent.parent / "debug"
# Ein fehlgeschlagener Scraper wird nach dieser Pause einmal wiederholt (Seite gerade in
# Bearbeitung, kurzer Aussetzer o. Ä.). Tests setzen das auf 0.
RETRY_DELAY = 20
log = logging.getLogger("scraper")



def load_old(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {r["id"]: r for r in data.get("restaurants", [])}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Alte menu.json nicht lesbar (%s) – starte ohne Altdaten", exc)
        return {}


def _merge_past_days(new: dict, old: dict | None, today: date | None = None) -> None:
    """Bereits gesehene Tage der laufenden Woche (bis einschließlich heute) behalten,
    wenn die Quelle sie nicht mehr enthält. Betrifft z. B. Osfizio (zeigt nur den
    aktuellen Tag) und Lercherl (stellt schon Freitagnachmittag auf die Folgewoche um –
    sonst wäre das heutige Menü weg). Künftige Tage kommen nur aus der Quelle."""
    if not old:
        return
    today = today or today_vienna()
    week_start, today_iso = monday_of(today).isoformat(), today.isoformat()
    have = {d["date"] for d in new["days"]}
    kept = [d for d in old.get("days", [])
            if week_start <= d["date"] <= today_iso and d["date"] not in have]
    if kept:
        new["days"] = sorted(new["days"] + kept, key=lambda d: d["date"])


def _attempt(scrape: Callable[[], RestaurantMenu]) -> RestaurantMenu:
    menu = scrape()
    if not menu.days and not menu.flyer_url:
        raise ValueError("Keine Menüdaten gefunden – Seitenstruktur geändert?")
    return menu


def _dump_debug(debug_dir: Path, rid: str, msg: str) -> None:
    """Zuletzt geladene Seiten speichern, damit man später sieht, was der Server geliefert hat."""
    try:
        target = debug_dir / rid
        target.mkdir(parents=True, exist_ok=True)
        lines = [msg, ""]
        for n, (url, status, body) in enumerate(common.recent_responses(), 1):
            name = f"{n:02d}_" + (re.sub(r"[^\w.-]+", "_", url.split("://", 1)[-1])[:80] or "seite")
            (target / name).write_bytes(body)
            lines.append(f"{name}: HTTP {status} {url} ({len(body)} Bytes)")
        (target / "fehler.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        log.warning("Diagnose-Dateien für %s nicht geschrieben: %s", rid, exc)


def run_one(module: Any, old: dict | None, scrape: Callable[[], RestaurantMenu] | None = None,
            debug_dir: Path | None = None) -> dict:
    """Ein Restaurant scrapen (bei Fehler ein zweiter Versuch); scheitert auch der,
    Altdaten als stale zurückgeben und – falls debug_dir – die geladenen Seiten speichern."""
    scrape = scrape or module.scrape
    try:
        common.reset_recent()
        try:
            menu = _attempt(scrape)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: 1. Versuch fehlgeschlagen (%s: %s) – neuer Versuch in %ss",
                        module.ID, type(exc).__name__, exc, RETRY_DELAY)
            time.sleep(RETRY_DELAY)
            menu = _attempt(scrape)
        menu.fetched_at = iso_now()
        menu.stale = False
        menu.error = None
        result = menu.to_dict()
        _merge_past_days(result, old)
        return result
    except Exception as exc:  # noqa: BLE001 – Isolation ist hier der Zweck
        msg = f"{type(exc).__name__}: {exc}"
        log.error("%s fehlgeschlagen: %s", module.ID, msg)
        if debug_dir:
            _dump_debug(debug_dir, module.ID, msg)
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


def build(modules: Iterable[Any], old_by_id: dict[str, dict], debug_dir: Path | None = None) -> dict:
    restaurants = [run_one(m, old_by_id.get(m.ID), debug_dir=debug_dir) for m in modules]
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
    parser.add_argument("--debug-dir", type=Path, default=DEFAULT_DEBUG_DIR,
                        help="hier landen bei Fehlern die geladenen Seiten (Standard: debug/)")
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
    data = build(modules, old_by_id, args.debug_dir)

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

    problems = health.check(data, now_vienna())
    for prob in problems:
        log.warning("%s", prob)
    report_to_github(problems)

    ok = sum(1 for r in data["restaurants"] if not r["stale"])
    return 0 if ok else 1


def report_to_github(problems: list) -> None:
    """In GitHub Actions: Zusammenfassung in den Lauf schreiben und die Probleme als
    Step-Output weitergeben (der Job 'health' macht daraus den Alarm)."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(health.markdown(problems))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        text = "\n".join(map(str, problems))
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"problems={len(problems)}\n")
            fh.write(f"problem_text<<__EOF__\n{text}\n__EOF__\n")


if __name__ == "__main__":
    sys.exit(main())
