"""Registry aller Restaurants. Neues Restaurant: Modul anlegen (ID, NAME, URL, scrape())
und hier in RESTAURANTS eintragen – die Reihenfolge ist die Standard-Reihenfolge der Seite."""
from . import fruga, interspar, lercherl, osfizio

RESTAURANTS = [lercherl, osfizio, fruga, interspar]
