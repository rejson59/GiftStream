from app import gifts
from app.models import TikTokEvent


def test_catalog_merges_real_gift_image_and_searches_by_localized_name(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    gifts.record_event(TikTokEvent(type="gift", user="viewer", gift_id=801, gift_name="Rose",
                                  gift_image_url="https://p16-webcast.tiktokcdn.com/gift.png",
                                  diamonds=1, source="tiktok"))
    rose = next(g for g in gifts.list_gifts("rose") if g.get("id") == 801)
    assert rose["image_url"] == "https://p16-webcast.tiktokcdn.com/gift.png"
    assert rose["source"] == "tiktok-live"
    assert rose["coins"] == 0
    assert rose["coins_estimated"] is True
    assert gifts.list_gifts("not-a-gift") == []


def test_older_diamond_based_coin_prices_are_invalidated_on_cache_load(tmp_path, monkeypatch):
    path = tmp_path / "gifts.json"
    path.write_text('[{"id": 44, "name": "Old Estimate", "diamonds": 100, "coins": 100, "coins_estimated": true}]', encoding="utf-8")
    monkeypatch.setattr(gifts, "CACHE_PATH", path)
    cache = gifts._load_cache()
    assert cache["44"]["coins"] == 0
    assert cache["44"]["coins_estimated"] is True


def test_catalog_prices_are_exposed_as_coins_and_sort_options_work(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    popular = gifts.list_gifts(sort="popular")
    cheap = gifts.list_gifts(sort="price_asc")
    expensive = gifts.list_gifts(sort="price_desc")
    assert popular[0]["name"] == "Rose"
    assert all(gift["coins"] == 0 and gift["coins_estimated"] for gift in cheap)
    assert all(gift["coins"] == 0 for gift in expensive)
    assert all("coins" in gift for gift in popular)


def test_catalog_prefers_explicit_coin_cost_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    gifts.record_metadata({"id": 812, "name": "Coin Test", "coin_count": 12,
                           "diamond_count": 6, "image": {"url_list": []}}, save=False)
    item = next(gift for gift in gifts.list_gifts() if gift["name"] == "Coin Test")
    assert item["coins"] == 12
    assert item["coins_estimated"] is False
    assert item["diamonds"] == 6


def test_coin_price_lookup_never_claims_estimated_diamond_values_as_purchase_coins(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    assert gifts.coin_price_for_gift(None, "Rose") == (0, True)
    gifts.record_metadata({"id": 813, "name": "Verified Coin Gift", "coin_count": 45,
                           "diamond_count": 9, "image": {"url_list": []}}, save=False)
    assert gifts.coin_price_for_gift(813, "Verified Coin Gift") == (45, False)
    assert gifts.coin_price_for_gift(999999, "Unknown") == (0, True)


def test_catalog_rejects_non_tiktok_image_url(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    gifts.record_event(TikTokEvent(type="gift", user="viewer", gift_id=802, gift_name="Rose",
                                  gift_image_url="https://evil.example/pixel.png", source="webhook"))
    assert next(g for g in gifts.list_gifts() if g.get("id") == 802)["image_url"] is None


def test_public_catalog_keeps_a_broader_catalog_with_tiktok_art(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    entries = [{
        "id": i + 1000,
        "name": "Rose" if i == 0 else f"Gift {i}",
        "diamond_count": i + 1,
        "image": {"url_list": [f"https://p16-webcast.tiktokcdn.com/gift-{i}.webp"]},
    } for i in range(125)]
    assert gifts.record_catalog({"gifts": entries}) == 125
    catalog = gifts.list_gifts()
    assert len(catalog) == 125
    assert all(gift["source"] == "tiktok-catalog" and gift["image_url"].startswith("https://") for gift in catalog)
    rose = next(gift for gift in catalog if gift["name"] == "Rose")
    assert rose["id"] == 1000
    assert rose["coins"] == 0
    assert rose["coins_estimated"] is True
    assert len(list((tmp_path).glob("gifts.json"))) == 1


def test_public_catalog_keeps_untrusted_art_hidden_and_preserves_offline_examples(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    count = gifts.record_catalog([{
        "id": 3, "name": "Fake gift", "diamond_count": 1,
        "image": {"url_list": ["https://images.example/fake.webp"]},
    }])
    assert count == 1
    catalog = gifts.list_gifts()
    fake = next(gift for gift in catalog if gift.get("id") == 3)
    assert fake["image_url"] is None and fake["name"] == "Fake gift"
    assert any(gift["source"] == "sample" for gift in catalog)


def test_public_catalog_keeps_gifts_without_art_and_catalog_refresh_preserves_live_price(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    gifts.record_event(TikTokEvent(type="gift", user="viewer", gift_id=42, gift_name="Sample",
                                  gift_coins=12, gift_coins_estimated=False))
    assert gifts.record_catalog([{"id": 42, "name": "Sample", "diamond_count": 9}]) == 1
    item = next(g for g in gifts.list_gifts() if g.get("id") == 42)
    assert item["image_url"] is None
    assert item["coins"] == 12 and item["coins_estimated"] is False
    assert item["coin_source"] == "live-event"
