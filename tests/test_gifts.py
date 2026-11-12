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
    assert gifts.list_gifts("not-a-gift") == []


def test_catalog_rejects_non_tiktok_image_url(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    gifts.record_event(TikTokEvent(type="gift", user="viewer", gift_id=802, gift_name="Rose",
                                  gift_image_url="https://evil.example/pixel.png", source="webhook"))
    assert next(g for g in gifts.list_gifts() if g.get("id") == 802)["image_url"] is None


def test_public_catalog_keeps_100_popular_gifts_with_real_tiktok_art(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    entries = [{
        "id": i + 1000,
        "name": "Rose" if i == 0 else f"Gift {i}",
        "diamond_count": i + 1,
        "image": {"url_list": [f"https://p16-webcast.tiktokcdn.com/gift-{i}.webp"]},
    } for i in range(125)]
    assert gifts.record_catalog({"gifts": entries}) == 100
    catalog = gifts.list_gifts()
    assert len(catalog) == 100
    assert all(gift["source"] == "tiktok-catalog" and gift["image_url"].startswith("https://") for gift in catalog)
    assert next(gift for gift in catalog if gift["name"] == "Rose")["id"] == 1000
    assert len(list((tmp_path).glob("gifts.json"))) == 1


def test_public_catalog_ignores_untrusted_art_and_preserves_offline_examples(tmp_path, monkeypatch):
    monkeypatch.setattr(gifts, "CACHE_PATH", tmp_path / "gifts.json")
    monkeypatch.setattr(gifts, "_seen", {})
    count = gifts.record_catalog([{
        "id": 3, "name": "Fake gift", "diamond_count": 1,
        "image": {"url_list": ["https://images.example/fake.webp"]},
    }])
    assert count == 0
    assert any(gift["source"] == "sample" for gift in gifts.list_gifts())
