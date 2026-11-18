# MAhlzeit 11 – Antrag auf Mittagessen

Statische Web-App, die werktags die Mittagsmenüs von vier Restaurants einsammelt und auf
einer Seite zeigt. Das Crawlen übernimmt eine GitHub Action, gehostet wird auf GitHub Pages.

| Restaurant | Quelle | Was geparst wird |
|---|---|---|
| Lercherl | [wochenmenue.html](https://www.lercherl.at/wochenmenue.html) | Wochenmenü (HTML), Inline-Preise, Freitags-Spezial |
| Osfizio | [mittagsmenus](https://www.osfizio.at/mittagsmenus/) | nur der aktuelle Tag (Elementor-Tabs, Fallback og:description) |
| Fruga Vital | [frugavital.at](https://frugavital.at/) | Tabelle „Aktueller Speiseplan“, Fallback Wochen-PDF |
| Interspar | [flugblatt.interspar.at](https://flugblatt.interspar.at/menuplane/) | iPaper-Flugblatt → PDF (pdfplumber), Fallback Seitentext, dann Link + Vorschaubild |

## Aufbau

```
scraper/                 Python 3.12
  __main__.py            Runner: alle Scraper isoliert, Stale-Merge, schreibt site/data/menu.json
  common.py              HTTP (User-Agent, Timeout, Retry), Preise, deutsche Datumsangaben
  models.py              RestaurantMenu / Day / Item
  restaurants/           ein Modul pro Restaurant, jeweils scrape() -> RestaurantMenu
  tests/                 pytest + gespeicherte HTML-/PDF-Fixtures
site/                    reines HTML/CSS/JS, kein Build-Step
  data/menu.json         Ergebnis des Scrapers
.github/workflows/scrape.yml
```

Fällt ein Scraper aus, bleiben die letzten erfolgreichen Daten dieses Restaurants erhalten
(`stale: true`, `error` gesetzt). Die Seite zeigt das dezent an („Stand: Mo 10:30, aktuelle
Daten nicht verfügbar“). `menu.json` wird nur neu geschrieben, wenn sich der Inhalt geändert hat.

## Lokal laufen lassen

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -r scraper/requirements.txt

python -m scraper && python -m http.server -d site
# -> http://localhost:8000
```

Nützliche Optionen: `python -m scraper --only interspar -v` (nur ein Restaurant, ausführliches Log),
`--output pfad/menu.json`.

Tests: `python -m pytest scraper/tests -q`

## Ein Restaurant hinzufügen

1. `scraper/restaurants/<id>.py` anlegen mit `ID`, `NAME`, `URL` und `scrape() -> RestaurantMenu`.
   Bewährt hat sich die Trennung in eine reine Funktion `parse(html, ref_date)` (testbar) und
   ein dünnes `scrape()`, das nur herunterlädt (`common.fetch_text` / `common.fetch`).
2. Das Modul in `scraper/restaurants/__init__.py` in `RESTAURANTS` eintragen.
   Die Reihenfolge dort ist die Standardreihenfolge auf der Seite.
3. Die aktuelle Seite als Fixture unter `scraper/tests/fixtures/` speichern und
   `scraper/tests/test_<id>.py` schreiben.
4. `python -m scraper --only <id> -v` ausführen und `site/data/menu.json` prüfen.

Hilfreich aus `common.py`: `parse_german_date("Montag, 9.11.", ref)` (Jahr wird ergänzt),
`parse_price("€ 10,90")`, `split_allergens_in_parens("Pasta (A, C)")`, `clean()`.

### Datenformat (`site/data/menu.json`)

```json
{
  "schema_version": 1,
  "generated_at": "2026-11-12T09:31:02+01:00",
  "timezone": "Europe/Vienna",
  "restaurants": [{
    "id": "interspar", "name": "Interspar", "source_url": "…",
    "fetched_at": "…", "stale": false, "error": null,
    "notes": ["Mittagsmenü mit Suppe oder Menüsalat"],
    "flyer_url": "…", "preview_image": "…", "valid_from": "2026-11-09", "valid_to": "2026-11-14",
    "days": [{ "date": "2026-11-12", "items": [
      { "label": "Vegetarisch", "name": "…", "price": 8.4, "allergens": "A, F, M",
        "vegetarian": true, "description": "optional", "tags": ["vegan"] }
    ]}]
  }]
}
```

`flyer_url`, `preview_image`, `valid_from/valid_to`, `description` und `tags` sind optional.

## GitHub Pages einrichten

1. Repository auf GitHub anlegen und pushen (Branch `main`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions: „Read and write permissions“**,
   damit die Action `menu.json` committen darf.
4. Unter **Actions → „Menüs crawlen & Seite deployen“ → Run workflow** einmal manuell starten.

Zeitplan (UTC): So–Do 18:30 sowie Mo–Fr 01:30, 04:30, 06:30, 08:30 und 10:15 – in Wien eine
bzw. zwei Stunden später. GitHub startet geplante Läufe oft stark verspätet (beobachtet: mehrere
Stunden). Die Abend- und Nachtläufe sorgen dafür, dass die Wochenmenüs (die meist Tage vorher
online sind) und am Vorabend veröffentlichte Tagesmenüs trotzdem rechtzeitig da sind. Die
Läufe am Vormittag erwischen Tagesmenüs, die erst dann online gehen (Osfizio). Läufe ohne
Änderung erzeugen keinen Commit. Änderungen unter `site/` lösen beim Push nur ein Deploy ohne
Crawl aus.

### Überwachung & Benachrichtigung

Nach jedem Crawl prüft `scraper/health.py` das Ergebnis. Der Job `health` lässt den Lauf
fehlschlagen – und GitHub schickt dir eine Mail –, wenn

- ein Restaurant nicht geladen werden konnte (**Fehler**, die Seite zeigt dann ältere Daten),
- an einem Werktag ab 11:00 Uhr (Wien) für ein Restaurant kein Menü für heute da ist
  (**Warnung**: Seite nicht aktualisiert oder Parser findet nichts mehr),
- Interspar nur als Flugblatt-Link statt mit Gerichten vorliegt,
- ein Parser-Test rot ist oder Crawl/Deploy abbricht.

Daten werden trotzdem gespeichert und die Seite trotzdem veröffentlicht – der Alarm kommt erst am Ende.
Wochenenden, österreichische Feiertage sowie 24./31.12. lösen keine Warnung aus. Läufe vor 11:00
warnen nur bei echten Fehlern, nicht bei fehlenden Tagesmenüs.

Die Probleme stehen in der Zusammenfassung des Laufs (Actions → Lauf öffnen). Mails kommen laut
GitHub-Standard an das Konto, das den Zeitplan zuletzt geändert hat; einstellbar unter
**GitHub → Settings → Notifications → Actions** („Only notify for failed workflows“).
Zum Ausprobieren: **Actions → Run workflow → „Testalarm auslösen“** anhaken.

Lokal erscheinen dieselben Hinweise als `WARNING` im Log von `python -m scraper`.

Scheitert ein Scraper, wird er nach 20 s einmal wiederholt. Scheitert er wieder, speichert der
Runner die zuletzt geladenen Seiten samt HTTP-Status unter `debug/<restaurant>/` (lokal, in
`.gitignore`). Im Workflow landen sie als Artefakt **„diagnose-…“** im Lauf (14 Tage) – so sieht
man, was der Server tatsächlich geliefert hat.

> Hinweis: GitHub pausiert geplante Workflows in Repos, die 60 Tage keine Aktivität hatten.
> Die automatischen `menu.json`-Commits halten das Repo normalerweise aktiv.

## Hinweise zu den Quellen

- **Interspar:** Die Flugblatt-URL ist `menuplan-kw{N}` (ohne führende Null bei KW 46/47 bestätigt;
  der Scraper probiert für einstellige KWs zusätzlich `kw0N`). Alte Wochen werden gelöscht (404),
  die nächste Woche steht meist schon ab Donnerstag online und wird als Vorschau mitgeladen.
  Das PDF kommt per GET von `…/menuplan-kwNN/GetPDF.ashx`. Die Übersichtsseite
  `interspar.at/gastronomie/restaurant-menueplan` ist per Cloudflare-Challenge gesperrt und
  daher kein automatischer Fallback. Das Flugblatt nennt keine Filiale – es gibt nur eine
  österreichweite URL.
- **Osfizio** stellt nur den aktuellen Tag online, teils erst gegen 10:45. Bereits gesehene Tage
  der Woche werden in `menu.json` behalten, damit man zurückblättern kann. Manchmal bleibt das
  Menü vom Vortag unter dem aktuellen im Tab stehen – Blöcke vor heute werden ignoriert.
  Gerichte können über mehrere Zeilen gehen (Zeile ohne führenden Strich = Fortsetzung).
- Alle Abrufe mit eigenem User-Agent, 20 s Timeout, höchstens ein Retry – sechs Läufe pro Werktag.
