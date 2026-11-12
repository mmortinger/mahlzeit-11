"""Datenmodell für menu.json."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class Item:
    label: str
    name: str
    price: float | None = None
    allergens: str | None = None
    vegetarian: bool | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class Day:
    date: str  # ISO "YYYY-MM-DD"
    items: list[Item] = field(default_factory=list)


@dataclass
class RestaurantMenu:
    id: str
    name: str
    source_url: str
    days: list[Day] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fetched_at: str | None = None
    stale: bool = False
    error: str | None = None
    # Kurzinfo, die auf der Karte immer sichtbar ist (z. B. "Alle Menüs mit Tagessuppe")
    subtitle: str | None = None
    # Erklärung, wenn für heute/künftige Tage (noch) nichts da ist (z. B. "erst am Vormittag online")
    empty_hint: str | None = None
    flyer_url: str | None = None
    preview_image: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Optionale Felder nur ausgeben, wenn gesetzt -> schlankeres JSON
        for key in ("subtitle", "empty_hint", "flyer_url", "preview_image", "valid_from", "valid_to"):
            if d[key] is None:
                del d[key]
        for day in d["days"]:
            for item in day["items"]:
                if item["description"] is None:
                    del item["description"]
                if not item["tags"]:
                    del item["tags"]
        return d
