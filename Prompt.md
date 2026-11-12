# Projekt: „MAhlzeit 11" – Mittagsmenü-Aggregator (statisch, GitHub Pages)

## Ziel
Eine statische Web-App, die jeden Werktag die Mittagsmenüs von 4 Restaurants crawlt und schön auf einer Seite anzeigt. Gehostet auf GitHub Pages, das Crawlen läuft über GitHub Actions.

- App-Name: **MAhlzeit 11** (genau so schreiben, mit großem „A")
- Untertitel: **Antrag auf Mittagessen**
- Logo: `logo.jpg` im Repo-Root (Wal mit Kochmütze, Linien in Dunkelblau ~#0B4F82, Akzente in Hellblau ~#B5CFE6, weißer Hintergrund). Daraus auch das Favicon machen.

## Architektur
- Kein Scraping im Browser (CORS). Stattdessen:
  - `scraper/` – Python 3.12, ein Modul pro Restaurant, gemeinsames Interface `scrape() -> RestaurantMenu`
  - Output: `site/data/menu.json` (Schema siehe unten)
  - `site/` – reines HTML/CSS/Vanilla-JS (kein Framework, kein Build-Step), lädt `data/menu.json`
- GitHub Action `.github/workflows/scrape.yml`:
  - Cron Mo–Fr um 06:30 und 08:30 UTC (deckt Sommer-/Winterzeit ab; das Mittagsmenü soll in Wien ab ca. 09:30 stehen) + `workflow_dispatch`
  - Läuft die Scraper, committet `menu.json` nur bei Änderungen, und deployt danach `site/` auf GitHub Pages (actions/deploy-pages)
- Jeder Scraper ist isoliert: Fällt einer aus, schreiben die anderen trotzdem. Bei einem Fehler: die letzten erfolgreichen Daten dieses Restaurants behalten (aus der alten menu.json), mit `stale: true` markieren und `error` setzen.

## JSON-Schema (Vorschlag, gern verbessern)
```json
{
  "generated_at": "ISO-8601",
  "restaurants": [{
    "id": "lercherl",
    "name": "Lercherl",
    "source_url": "...",
    "fetched_at": "ISO-8601",
    "stale": false,
    "error": null,
    "notes": ["Mo–Fr mit Suppe € 9,90", "Täglich: Wiener Schnitzel ..."],
    "days": [{
      "date": "2026-11-12",
      "items": [{ "label": "Menü 1", "name": "...", "price": 11.90, "allergens": "A, G", "vegetarian": null }]
    }]
  }]
}
```

## Quellen & Parsing-Hinweise (vorher selbst ansehen und verifizieren!)

1. **Lercherl** – https://www.lercherl.at/wochenmenue.html
   HTML. Ein Abschnitt pro Tag (mit Datum): Tagessuppe, Hauptgericht, „oder", Alternative. Standardpreis € 9,90 im Kopf („Montag bis Freitag, mit Suppe"); abweichende Preise inline (z. B. Fisch Freitag). Dauerhaftes Alternativgericht (Wiener Schnitzel) und „Freitags-Spezial" als eigene Einträge/Notizen erfassen.

2. **Osfizio** – https://www.osfizio.at/mittagsmenus/
   HTML. Pro Tag zwei Menüs: „1-Mittagsmenü" (€ 11,90) und „2-Mittagsmenü" (€ 10,90), jeweils Vorspeise (Salat/Suppe) + Hauptgericht, mit Allergen-Codes in Klammern. Es steht vermutlich nur der aktuelle Tag online. Das Datum steht evtl. nur in der meta description, Gerichte im Body prüfen. Keine Wochenvorschau, daher nur `days` für heute.

3. **Fruga Vital** – https://frugavital.at/
   HTML-Tabelle unter „Aktueller Speiseplan" (Tag mit Datum, Gericht, Preis; 2–4 Gerichte/Tag, Mo–Sa). Zusätzlich verlinkte Wochen-PDFs (`/wp-content/uploads/YYYY/MM/Fruga_Vital_Speiseplan_DDMMYYYY.pdf`). Primär die HTML-Tabelle nutzen, PDF nur als Fallback. Schnitzel/Kabeljau „außerhalb des Menüs" als Notiz.

4. **Interspar** – aktuell https://flugblatt.interspar.at/menuplane/menuplan-kw46/
   Achtung: iPaper-Flugblatt-Viewer, kein Menütext im HTML. Die URL ändert sich pro Woche:
   - URL aus der ISO-Kalenderwoche bauen (`menuplan-kw{NN}`, prüfen ob mit führender Null), Fallback: Übersichtsseite https://www.interspar.at/gastronomie/restaurant-menueplan nach dem aktuellen Link durchsuchen.
   - Das PDF finden (iPaper hat einen „Download PDF"-Button; Netzwerk/HTML/iPaper-Endpunkte untersuchen) und mit `pdfplumber` Text extrahieren. Falls das PDF nur Bilder enthält: KEIN OCR-Zwang. Dann `days` leer lassen und in der UI Link zum Flugblatt + `og:image`-Vorschau anzeigen.
   - Prüfen, ob der Plan filialspezifisch ist; falls ja, mir Bescheid geben.

Allgemein: `requests` + `BeautifulSoup`, eigener User-Agent, Timeout, keine aggressive Frequenz. Datums-Parsing robust für deutsche Formate („Montag, 9.11." ohne Jahr → Jahr aus der aktuellen Woche ableiten). Preise als float.

## Frontend
- Mobile-first, eine Seite. Header mit Logo, „MAhlzeit 11", Untertitel „Antrag auf Mittagessen".
- Standardansicht: **heute**, als Karte pro Restaurant (Name, Gerichte mit Preis, Allergene klein/dezent, Link zur Quelle). Tages-Tabs Mo–Fr zum Durchklicken der Woche; Restaurants ohne Daten für den Tag zeigen „Kein Menü für diesen Tag – zur Website".
- Am Wochenende/vor dem Crawl: nächsten Werktag bzw. Hinweis anzeigen.
- `stale`/`error` dezent kennzeichnen („Stand: Mo 10:30, aktuelle Daten nicht verfügbar").
- „Zuletzt aktualisiert"-Zeitstempel in Europe/Vienna.
- Design: frisch, freundlich, passend zum Logo: Weiß/Hellgrau-Hintergrund, Dunkelblau als Primärfarbe, Hellblau als Akzent, abgerundete Karten, gut lesbare Typografie. Dark Mode via `prefers-color-scheme`. Keine externen Tracker; Fonts lokal oder System-Fonts.
- Optional, wenn einfach: Restaurant-Reihenfolge per Drag/Klick merken (localStorage, try/catch).

## Qualität
- `pytest` mit gespeicherten HTML-/PDF-Fixtures pro Restaurant (jetzt einmal abrufen und unter `scraper/tests/fixtures/` ablegen), damit Parser-Änderungen testbar sind.
- README: Setup, lokal laufen lassen (`python -m scraper && python -m http.server -d site`), wie man ein Restaurant hinzufügt, GitHub-Pages-Einrichtung (Settings → Pages → Source: GitHub Actions).
- Am Ende: Scraper einmal live laufen lassen, `menu.json` prüfen, Seite lokal öffnen und mir zeigen, was bei jedem Restaurant rauskommt, inkl. der Ergebnisse zu Interspar.

Bitte zuerst die vier Seiten selbst untersuchen und kurz berichten, falls etwas von den Hinweisen oben abweicht, dann bauen.