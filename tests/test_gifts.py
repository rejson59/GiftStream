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
