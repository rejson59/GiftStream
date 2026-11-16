"""Testy przycinania dźwięków (0.20.0): WAV, fade, podgląd fali i bezpieczne pobieranie linku."""
import math
import struct
from array import array
from urllib.parse import urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import audio as audio_tools
from app import main


def build_wav(data: bytes, bits: int = 16, fmt: int = 1, rate: int = 22050, channels: int = 1) -> bytes:
    block = channels * (4 if fmt == 3 else max(1, bits // 8))
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " +
            struct.pack("<IHHIIHH", 16, fmt, channels, rate, rate * block, block, bits) +
            b"data" + struct.pack("<I", len(data)) + data)


def tone(seconds: float, rate: int = 22050, channels: int = 1, amplitude: int = 12000) -> bytes:
    samples = array("h", [int(amplitude * math.sin(2 * math.pi * 330 * i / rate))
                          for i in range(int(seconds * rate) * channels)])
    return build_wav(samples.tobytes(), rate=rate, channels=channels)


@pytest.fixture
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_SOUND_UPLOAD_DIR", tmp_path / "uploads")
    return tmp_path / "uploads"


def test_wav_info_reports_duration_and_channels():
    info = audio_tools.wav_info(tone(2.5))
    assert info["duration"] == pytest.approx(2.5, abs=0.01)
    assert info["channels"] == 1
    assert info["sample_rate"] == 22050
    assert info["bits"] == 16


def test_trim_cuts_the_selected_fragment():
    trimmed, info = audio_tools.trim_wav(tone(5.0), start=1.0, end=3.0)
    assert info["duration"] == pytest.approx(2.0, abs=0.02)
    assert info["start"] == pytest.approx(1.0)
    assert audio_tools.wav_info(trimmed)["duration"] == pytest.approx(2.0, abs=0.02)


def test_trim_clamps_long_selections_to_the_alert_limit():
    _trimmed, info = audio_tools.trim_wav(tone(30.0), start=0, end=25.0)
    assert info["duration"] == pytest.approx(audio_tools.MAX_CLIP_SECONDS, abs=0.05)


def test_trim_rejects_tiny_and_invalid_ranges():
    with pytest.raises(audio_tools.AudioError):
        audio_tools.trim_wav(tone(3.0), start=1.0, end=1.01)
    with pytest.raises(audio_tools.AudioError):
        audio_tools.trim_wav(b"to nie jest wav")


def test_trim_fades_start_and_end_of_the_clip():
    trimmed, _info = audio_tools.trim_wav(tone(4.0), start=0.5, end=1.5, fade_in_ms=200, fade_out_ms=200)
    fmt, _data = audio_tools._read_chunks(trimmed)
    samples = audio_tools._decode_samples(fmt)
    peak = max(abs(value) for value in samples)
    assert abs(samples[0]) < peak * 0.05, "fade in musi zaczynać się od ciszy"
    assert abs(samples[-1]) < peak * 0.05, "fade out musi kończyć się ciszą"


def test_trim_supports_stereo_8_and_24_bit_files():
    stereo = tone(1.0, channels=2)
    trimmed, info = audio_tools.trim_wav(stereo, start=0.1, end=0.6)
    assert info["channels"] == 2
    assert audio_tools.wav_info(trimmed)["channels"] == 2

    eight = build_wav(bytes([128 + int(90 * math.sin(i / 4)) for i in range(8000)]), bits=8, rate=8000)
    _clip, info = audio_tools.trim_wav(eight, start=0.2, end=0.7)
    assert info["duration"] == pytest.approx(0.5, abs=0.02)

    frames = 8000
    payload = bytearray()
    for index in range(frames):
        value = int(4_000_000 * math.sin(2 * math.pi * 100 * index / 8000))
        value = value if value >= 0 else value + 0x1000000
        payload += bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))
    _clip, info = audio_tools.trim_wav(build_wav(bytes(payload), bits=24, rate=8000), start=0, end=0.25)
    assert info["duration"] == pytest.approx(0.25, abs=0.02)


def test_peaks_are_normalised_for_the_waveform_preview():
    peaks = audio_tools.wav_peaks(tone(2.0), buckets=32)
    assert len(peaks) == 32
    assert max(peaks) == pytest.approx(1.0)
    assert all(0.0 <= value <= 1.0 for value in peaks)


def test_info_and_trim_endpoints_save_a_playable_file(isolated_uploads):
    client = TestClient(main.app)
    source = tone(6.0)
    info = client.post("/api/sounds/info?filename=test.wav", content=source)
    assert info.status_code == 200
    assert info.json()["duration"] == pytest.approx(6.0, abs=0.02)
    assert len(info.json()["peaks"]) == 180

    trimmed = client.post("/api/sounds/trim?start=1&end=4&fade_in_ms=100&fade_out_ms=200&filename=test.wav",
                          content=source)
    assert trimmed.status_code == 200
    body = trimmed.json()
    assert body["duration"] == pytest.approx(3.0, abs=0.02)
    assert body["name"].startswith("test · ")

    asset = client.get(body["url"])
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "audio/wav"
    assert audio_tools.wav_info(asset.content)["duration"] == pytest.approx(3.0, abs=0.02)


def test_trim_rejects_bad_ranges_and_non_audio(isolated_uploads):
    client = TestClient(main.app)
    source = tone(2.0)
    assert client.post("/api/sounds/trim?start=1&end=1", content=source).status_code == 422
    assert client.post("/api/sounds/trim?start=-1&end=1", content=source).status_code == 422
    assert client.post("/api/sounds/info", content=b"x" * 100).status_code == 415
    assert client.post("/api/sounds/trim?start=0&end=1", content=b"").status_code == 413


def test_uploaded_sounds_are_listed_with_duration(isolated_uploads):
    client = TestClient(main.app)
    client.post("/api/sounds/trim?start=0&end=1.5&filename=moj.wav", content=tone(3.0))
    listed = client.get("/api/sounds/uploads").json()["files"]
    assert len(listed) == 1
    assert listed[0]["duration"] == pytest.approx(1.5, abs=0.03)
    assert listed[0]["url"].startswith("/api/sounds/uploads/")


@pytest.mark.parametrize("url", [
    "http://cdn.example.org/sound.mp3",
    "https://127.0.0.1/sound.mp3",
    "https://localhost/sound.mp3",
    "https://[::1]/sound.mp3",
    "https://router.local/sound.mp3",
    "https://user:pass@cdn.example.org/sound.mp3",
])
def test_sound_fetch_rejects_unsafe_urls(url, isolated_uploads):
    with pytest.raises(HTTPException) as error:
        main._public_audio_url(url, "Link dźwięku")
    assert error.value.status_code == 422


def test_redirect_handler_blocks_a_redirect_to_localhost(monkeypatch):
    handler = main._AudioRedirect()
    with pytest.raises(Exception):
        handler.redirect_request(
            type("Req", (), {"full_url": "https://cdn.example.org/sound.mp3"})(), None, 302, "", {},
            "http://127.0.0.1:8000/api/config")


def test_sound_fetch_stores_a_local_copy(isolated_uploads, monkeypatch):
    monkeypatch.setattr(main, "_download_audio", lambda url: (
        {"payload": tone(1.0), "suffix": ".wav", "content_type": "audio/wav"}, "audio/wav"))
    client = TestClient(main.app)
    fetched = client.post("/api/sounds/fetch", json={"url": "https://cdn.example.org/a.wav", "name": "Mój dźwięk"})
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["name"] == "Mój dźwięk"
    assert body["url"].startswith("/api/sounds/uploads/")
    assert client.get(body["url"]).status_code == 200


def test_sound_fetch_reports_download_failures(isolated_uploads, monkeypatch):
    def boom(_url):
        raise ValueError("serwer nie odpowiada")

    monkeypatch.setattr(main, "_download_audio", boom)
    client = TestClient(main.app)
    response = client.post("/api/sounds/fetch", json={"url": "https://cdn.example.org/a.mp3"})
    assert response.status_code == 502
    assert "serwer nie odpowiada" in response.json()["detail"]


def test_static_sound_script_is_served():
    response = TestClient(main.app).get("/static/sounds.js")
    assert response.status_code == 200
    assert "GiftStreamSounds" in response.text
