"""Pure unit tests for apply_dashboard_overrides() - no DB, no network, same spirit as
test_merge.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dashboard_view import apply_dashboard_overrides
from app.db.repository import ResolvedDashboardItem


def _merged():
    return {
        "services": [
            {"id": 1, "name": "a.example.com", "vm": None},
            {"id": 2, "name": "b.example.com", "vm": None},
        ],
        "infrastructure": [
            {"node": "pve", "vmid": 100, "name": "standalone-vm", "status": "running"},
        ],
        "errors": {"npm": None, "proxmox": None},
    }


def _item(kind, key, item_id, *, visible=True, sort_order=0, custom_name=None,
          logo_url=None, category_id=None, custom_url=None):
    return ResolvedDashboardItem(
        kind=kind, key=key, item_id=item_id, category_id=category_id, visible=visible,
        sort_order=sort_order, custom_name=custom_name, logo_url=logo_url,
        custom_url=custom_url,
    )


def test_no_categories_reproduces_legacy_shape():
    # ports every assertion the pre-categories test suite made, just indexed via sections[0]/[1]
    # instead of result["services"]/["infrastructure"] - this is the one regression test that
    # actually matters: it must never change for a dashboard that hasn't adopted categories.
    items = [
        _item("proxy_host", 1, item_id=10, sort_order=5, custom_name="Custom A", logo_url="/api/logos/3/image"),
        _item("proxy_host", 2, item_id=20, sort_order=1),
        _item("guest", ("pve", 100), item_id=30, sort_order=0, custom_name="My VM"),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=[])

    assert [s["id"] for s in result["sections"]] == [None, None]
    assert [s["name"] for s in result["sections"]] == ["Dienste", "Infrastruktur"]

    services = result["sections"][0]["tiles"]
    infra = result["sections"][1]["tiles"]
    assert [s["id"] for s in services] == [2, 1]
    assert services[1]["name"] == "Custom A"
    assert services[0]["name"] == "b.example.com"  # untouched
    assert services[0]["logo_url"] is None
    assert services[1]["logo_url"] == "/api/logos/3/image"
    assert infra[0]["name"] == "My VM"
    assert result["errors"] == {"npm": None, "proxmox": None}

    # item_id/category_id must actually be on the tile dict, not just used internally for
    # sorting/grouping - the frontend's edit mode PATCHes by item_id, so a tile without it is a
    # silent, hard-to-notice bug (caught by hand in a real browser once already - see git history).
    assert services[0]["item_id"] == 20
    assert services[1]["item_id"] == 10
    assert all("category_id" in s for s in services)
    assert infra[0]["item_id"] == 30


def test_hidden_item_is_filtered_out():
    items = [
        _item("proxy_host", 1, item_id=10, visible=True),
        _item("proxy_host", 2, item_id=20, visible=False),
        _item("guest", ("pve", 100), item_id=30, visible=True),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    services = result["sections"][0]["tiles"]
    infra = result["sections"][1]["tiles"]
    assert [s["id"] for s in services] == [1]
    assert len(infra) == 1


def test_item_missing_from_dashboard_is_treated_as_hidden():
    items = [_item("proxy_host", 1, item_id=10)]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    assert [s["id"] for s in result["sections"][0]["tiles"]] == [1]
    assert result["sections"][1]["tiles"] == []


def test_type_discriminator_set():
    items = [
        _item("proxy_host", 1, item_id=10),
        _item("guest", ("pve", 100), item_id=30),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    assert result["sections"][0]["tiles"][0]["type"] == "service"
    assert result["sections"][1]["tiles"][0]["type"] == "infrastructure"


def test_categories_group_mixed_service_and_guest_tiles():
    categories = [{"id": 1, "name": "Media", "sort_order": 0}]
    items = [
        _item("proxy_host", 1, item_id=10, category_id=1, sort_order=1),
        _item("guest", ("pve", 100), item_id=30, category_id=1, sort_order=0),
        _item("proxy_host", 2, item_id=20, category_id=None),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=categories)

    # Dienste/Infrastruktur are permanent built-in sections - a category never replaces them,
    # it's just inserted ahead of them.
    assert [s["name"] for s in result["sections"]] == ["Media", "Dienste", "Infrastruktur"]
    media_tiles = result["sections"][0]["tiles"]
    assert [t["type"] for t in media_tiles] == ["infrastructure", "service"]  # sort_order 0 then 1
    assert [t["item_id"] for t in media_tiles] == [30, 10]
    assert [t["category_id"] for t in media_tiles] == [1, 1]
    assert result["sections"][1]["tiles"][0]["id"] == 2  # uncategorized service -> Dienste
    assert result["sections"][1]["tiles"][0]["item_id"] == 20
    assert result["sections"][1]["tiles"][0]["category_id"] is None
    assert result["sections"][2]["tiles"] == []  # no uncategorized guest here


def test_dienste_and_infrastruktur_always_present_even_when_empty():
    # unlike a custom category (only emitted if the admin created it), these two built-in
    # sections must never disappear, even if every single item ends up in a custom category.
    categories = [{"id": 1, "name": "Media", "sort_order": 0}]
    items = [
        _item("proxy_host", 1, item_id=10, category_id=1),
        _item("proxy_host", 2, item_id=20, category_id=1),
        _item("guest", ("pve", 100), item_id=30, category_id=1),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=categories)
    assert [s["name"] for s in result["sections"]] == ["Media", "Dienste", "Infrastruktur"]
    assert result["sections"][1]["tiles"] == []
    assert result["sections"][2]["tiles"] == []


def test_empty_category_still_emitted():
    # so an admin can drag something into a freshly-created, still-empty category
    categories = [{"id": 1, "name": "Media", "sort_order": 0}, {"id": 2, "name": "Empty", "sort_order": 1}]
    items = [_item("proxy_host", 1, item_id=10, category_id=1)]
    result = apply_dashboard_overrides(_merged(), items, categories=categories)
    assert [s["name"] for s in result["sections"]] == ["Media", "Empty", "Dienste", "Infrastruktur"]
    assert result["sections"][1]["tiles"] == []


def test_hidden_and_missing_items_excluded_under_categories():
    categories = [{"id": 1, "name": "Media", "sort_order": 0}]
    items = [
        _item("proxy_host", 1, item_id=10, category_id=1, visible=False),
        # host 2 has no item at all - missing entirely
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=categories)
    all_tiles = [t for s in result["sections"] for t in s["tiles"]]
    assert all_tiles == []


def test_orphaned_category_id_falls_back_to_uncategorized():
    # category_id pointing at a category not in the known list (e.g. stale reference) must not
    # silently disappear the tile - it lands in the built-in section matching its own type.
    categories = [{"id": 1, "name": "Media", "sort_order": 0}]
    items = [
        _item("proxy_host", 1, item_id=10, category_id=999),
        _item("guest", ("pve", 100), item_id=30, category_id=999),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=categories)
    assert [s["name"] for s in result["sections"]] == ["Media", "Dienste", "Infrastruktur"]
    assert result["sections"][1]["tiles"][0]["id"] == 1
    assert result["sections"][2]["tiles"][0]["name"] == "standalone-vm"


def test_sort_tie_break_by_item_id():
    # both default to sort_order=0 (as ensure_default_dashboard_items gives every newly-attached
    # item) - must resolve deterministically by item_id, not incidental iteration order.
    categories = [{"id": 1, "name": "Media", "sort_order": 0}]
    items = [
        _item("proxy_host", 2, item_id=99, category_id=1, sort_order=0),
        _item("proxy_host", 1, item_id=5, category_id=1, sort_order=0),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=categories)
    assert [t["id"] for t in result["sections"][0]["tiles"]] == [1, 2]  # item_id 5 before 99


def test_infra_tile_gets_href_from_custom_url():
    # a bare guest (no matching NPM proxy host, e.g. HomeAssistant) has no href at all coming out
    # of build_dashboard() - custom_url is the only way it ever gets a clickable link.
    items = [_item("guest", ("pve", 100), item_id=30, custom_url="http://homeassistant.local:8123")]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    infra = result["sections"][1]["tiles"]
    assert infra[0]["href"] == "http://homeassistant.local:8123"


def test_infra_tile_href_is_none_without_custom_url():
    items = [_item("guest", ("pve", 100), item_id=30)]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    assert result["sections"][1]["tiles"][0]["href"] is None


def test_custom_url_overrides_service_href():
    merged = _merged()
    merged["services"][0]["href"] = "https://a.example.com"
    items = [
        _item("proxy_host", 1, item_id=10, custom_url="https://a.example.com/custom-path"),
        _item("proxy_host", 2, item_id=20),
    ]
    result = apply_dashboard_overrides(merged, items, categories=[])
    services = {s["id"]: s for s in result["sections"][0]["tiles"]}
    assert services[1]["href"] == "https://a.example.com/custom-path"
    assert services[2]["href"] is None  # untouched - b.example.com never had one in this fixture


def test_matched_service_name_defaults_to_guest_name():
    # once matched, the guest's own name wins over the NPM subdomain by default - a domain is
    # often auto-generated/opaque, the guest name is what the admin actually calls the thing.
    merged = _merged()
    merged["services"][0]["vm"] = {"node": "pve", "vmid": 100, "name": "homarr", "kind": "lxc"}
    items = [_item("proxy_host", 1, item_id=10)]
    result = apply_dashboard_overrides(merged, items, categories=[])
    tile = result["sections"][0]["tiles"][0]
    assert tile["name"] == "homarr"


def test_matched_service_custom_name_still_overrides_guest_name():
    merged = _merged()
    merged["services"][0]["vm"] = {"node": "pve", "vmid": 100, "name": "homarr", "kind": "lxc"}
    items = [_item("proxy_host", 1, item_id=10, custom_name="My Dashboard")]
    result = apply_dashboard_overrides(merged, items, categories=[])
    tile = result["sections"][0]["tiles"][0]
    assert tile["name"] == "My Dashboard"


def test_unmatched_service_name_still_uses_npm_domain():
    # no vm at all (never matched) - the only name available is the one build_dashboard() gave.
    items = [_item("proxy_host", 2, item_id=20)]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    tile = result["sections"][0]["tiles"][0]
    assert tile["name"] == "b.example.com"


def test_custom_service_tile_synthesized_and_grouped_with_services():
    # a custom_service item has no merged["services"]/["infrastructure"] counterpart at all -
    # build_dashboard() never sees it - its tile is built entirely from the ResolvedDashboardItem
    # itself, and lands in "Dienste" (or a category) alongside real services, not Infrastruktur.
    items = [
        _item("custom_service", 42, item_id=50, custom_name="Fritzbox",
              custom_url="http://192.168.1.1", logo_url="/api/logos/7/image"),
    ]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    services = result["sections"][0]["tiles"]
    custom_tiles = [t for t in services if t["type"] == "custom"]
    assert len(custom_tiles) == 1
    tile = custom_tiles[0]
    assert tile["id"] == 42
    assert tile["name"] == "Fritzbox"
    assert tile["href"] == "http://192.168.1.1"
    assert tile["logo_url"] == "/api/logos/7/image"
    assert tile["item_id"] == 50
    assert tile["category_id"] is None


def test_hidden_custom_service_is_filtered_out():
    items = [_item("custom_service", 42, item_id=50, custom_name="Fritzbox", visible=False)]
    result = apply_dashboard_overrides(_merged(), items, categories=[])
    all_tiles = [t for s in result["sections"] for t in s["tiles"]]
    assert all(t.get("id") != 42 for t in all_tiles)


def test_original_dict_not_mutated():
    merged = _merged()
    items = [_item("proxy_host", 1, item_id=10, custom_name="Renamed", logo_url="/api/logos/9/image")]
    apply_dashboard_overrides(merged, items, categories=[])
    assert merged["services"][0]["name"] == "a.example.com"


if __name__ == "__main__":
    test_no_categories_reproduces_legacy_shape()
    test_hidden_item_is_filtered_out()
    test_item_missing_from_dashboard_is_treated_as_hidden()
    test_type_discriminator_set()
    test_categories_group_mixed_service_and_guest_tiles()
    test_dienste_and_infrastruktur_always_present_even_when_empty()
    test_empty_category_still_emitted()
    test_hidden_and_missing_items_excluded_under_categories()
    test_orphaned_category_id_falls_back_to_uncategorized()
    test_sort_tie_break_by_item_id()
    test_infra_tile_gets_href_from_custom_url()
    test_infra_tile_href_is_none_without_custom_url()
    test_custom_url_overrides_service_href()
    test_matched_service_name_defaults_to_guest_name()
    test_matched_service_custom_name_still_overrides_guest_name()
    test_unmatched_service_name_still_uses_npm_domain()
    test_custom_service_tile_synthesized_and_grouped_with_services()
    test_hidden_custom_service_is_filtered_out()
    test_original_dict_not_mutated()
    print("All dashboard_view tests passed.")
