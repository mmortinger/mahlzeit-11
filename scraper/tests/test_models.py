from scraper.models import Day, Item, RestaurantMenu


def test_optional_fields_omitted_when_empty():
    d = RestaurantMenu(id="x", name="X", source_url="u",
                       days=[Day(date="2026-11-12", items=[Item(label="M", name="N")])]).to_dict()
    for key in ("subtitle", "empty_hint", "flyer_url", "preview_image", "valid_from", "valid_to"):
        assert key not in d
    assert "description" not in d["days"][0]["items"][0] and "tags" not in d["days"][0]["items"][0]


def test_optional_fields_present_when_set():
    d = RestaurantMenu(id="x", name="X", source_url="u", subtitle="S", empty_hint="E").to_dict()
    assert d["subtitle"] == "S" and d["empty_hint"] == "E"
