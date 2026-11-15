"""WAV trimming and analysis without external tools.

GiftStream ships as a single EXE, so it cannot rely on ffmpeg or any audio
library outside the Python standard library. This module handles the most
common uncompressed format (WAV/PCM: 8, 16, 24 and 32 bit plus float32).

What it is for:
* ``wav_info`` — file duration and parameters (the panel shows the selection),
* ``trim_wav`` — cutting a fragment with a soft fade in and out,
* ``wav_peaks`` — waveform data for the Sound studio.

Compressed formats (MP3, M4A, OGG, FLAC) are trimmed in the browser, which
can decode them (``AudioContext.decodeAudioData``),
a wynik wraca do GiftStream jako gotowy WAV.
"""
from __future__ import annotations

import io
import struct
import sys
from array import array

MAX_CLIP_SECONDS = 12.0
_PCM = 1
_FLOAT = 3
_EXTENSIBLE = 0xFFFE


class AudioError(ValueError):
    """The file is not a supported WAV sound."""


def _scale(value: float, factor: float) -> float:
    """Scales a sample while keeping the array type (``array`` rejects floats)."""
    return value * factor if isinstance(value, float) else int(round(value * factor))


def _read_chunks(payload: bytes) -> tuple[dict, bytes]:
    if len(payload) < 12 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise AudioError("This is not a WAV file.")
    fmt: dict = {}
    data: bytes | None = None
    offset = 12
    while offset + 8 <= len(payload):
        chunk_id = payload[offset:offset + 4]
        size = struct.unpack_from("<I", payload, offset + 4)[0]
        body = payload[offset + 8:offset + 8 + size]
        if chunk_id == b"fmt ":
            if len(body) < 16:
                raise AudioError("The WAV header is incomplete.")
            audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack_from("<HHIIHH", body, 0)
            if audio_format == _EXTENSIBLE and len(body) >= 26:
                audio_format = struct.unpack_from("<H", body, 24)[0]
            fmt = {"format": audio_format, "channels": channels, "sample_rate": rate, "bits": bits}
        elif chunk_id == b"data":
            data = body
        offset += 8 + size + (size & 1)
    if not fmt or data is None:
        raise AudioError("The WAV file has no format header or no audio data.")
    if fmt["format"] == _FLOAT and fmt["bits"] != 32:
        raise AudioError("Only 32-bit floating point WAV is supported.")
    if fmt["format"] not in (_PCM, _FLOAT):
        raise AudioError("Only uncompressed WAV (PCM) files are supported.")
    if fmt["format"] == _PCM and fmt["bits"] not in (8, 16, 24, 32):
        raise AudioError("WAV PCM files with 8, 16, 24 and 32 bits are supported.")
    if not 1 <= fmt["channels"] <= 8:
        raise AudioError("The number of channels in the WAV file is not supported.")
    if not 4000 <= fmt["sample_rate"] <= 384000:
        raise AudioError("The sample rate of the WAV file is not supported.")
    fmt["data"] = data
    return fmt, data


def _decode_samples(fmt: dict) -> array:
    """Returns the samples as an ``array`` matching the file type (no 8-bit offset)."""
    data, bits, audio_format = fmt["data"], fmt["bits"], fmt["format"]
    if audio_format == _FLOAT:
        samples = array("f")
        samples.frombytes(data[: len(data) - (len(data) % 4)])
        if sys.byteorder == "big":
            samples.byteswap()
        return samples
    if bits == 8:
        return array("b", [value - 128 for value in data])
    kind = {16: "h", 24: "i", 32: "i"}[bits]
    if bits == 24:
        frames = len(data) // 3
        samples = array("i")
        for index in range(frames):
            start = index * 3
            value = data[start] | (data[start + 1] << 8) | (data[start + 2] << 16)
            if value & 0x800000:
                value -= 0x1000000
            samples.append(value)
        return samples
    samples = array(kind)
    samples.frombytes(data[: len(data) - (len(data) % (bits // 8))])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _encode_samples(samples: array, fmt: dict) -> bytes:
    bits, audio_format = fmt["bits"], fmt["format"]
    if audio_format == _FLOAT:
        out = array("f", samples)
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()
    if bits == 8:
        return bytes(max(0, min(255, int(round(value)) + 128)) for value in samples)
    if bits == 24:
        out = bytearray()
        for value in samples:
            value = max(-8388608, min(8388607, int(round(value))))
            if value < 0:
                value += 0x1000000
            out += bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))
        return bytes(out)
    kind = "h" if bits == 16 else "i"
    limit = (1 << (bits - 1)) - 1
    out = array(kind, [max(-limit - 1, min(limit, int(round(value)))) for value in samples])
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def _build_wav(samples: array, fmt: dict) -> bytes:
    payload = _encode_samples(samples, fmt)
    channels, rate, bits = fmt["channels"], fmt["sample_rate"], fmt["bits"]
    block_align = max(1, channels * max(1, bits // 8))
    if fmt["format"] == _FLOAT:
        block_align = channels * 4
    header = b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, fmt["format"], channels, rate,
                                    rate * block_align, block_align, bits)
    header += b"data" + struct.pack("<I", len(payload))
    return header + payload


def wav_info(payload: bytes) -> dict:
    """Basic WAV file information (without decoding the whole payload)."""
    fmt, data = _read_chunks(payload)
    block_align = max(1, fmt["channels"] * (4 if fmt["format"] == _FLOAT else max(1, fmt["bits"] // 8)))
    frames = len(data) // block_align
    return {
        "format": "wav",
        "channels": fmt["channels"],
        "sample_rate": fmt["sample_rate"],
        "bits": fmt["bits"],
        "frames": frames,
        "duration": round(frames / fmt["sample_rate"], 3),
        "size": len(payload),
    }


def trim_wav(payload: bytes, start: float = 0.0, end: float | None = None,
             fade_in_ms: int = 0, fade_out_ms: int = 0,
             max_seconds: float = MAX_CLIP_SECONDS) -> tuple[bytes, dict]:
    """Cuts a WAV fragment and returns ``(new_file, info)``.

    ``max_seconds`` caps the result — LIVE alerts are meant to be short, so a
    longer selection is trimmed automatically instead of blocking the save.
    """
    fmt, _data = _read_chunks(payload)
    info = wav_info(payload)
    rate, channels = fmt["sample_rate"], fmt["channels"]
    total_frames = info["frames"]
    duration = total_frames / rate

    start = max(0.0, min(float(start or 0.0), duration))
    end = duration if end is None else max(0.0, min(float(end), duration))
    if end - start < 0.05:
        raise AudioError("The fragment is too short — select at least 0.05 seconds.")
    if max_seconds > 0 and end - start > max_seconds:
        end = start + max_seconds

    samples = _decode_samples(fmt)
    first = int(round(start * rate)) * channels
    last = min(len(samples), int(round(end * rate)) * channels)
    clip = samples[first:last]
    frames = len(clip) // channels

    fade_in = min(max(0, int(fade_in_ms)), int(frames * 1000 / rate)) * rate // 1000 * channels
    fade_out = min(max(0, int(fade_out_ms)), int(frames * 1000 / rate)) * rate // 1000 * channels
    if fade_in > 0:
        for index in range(0, min(fade_in, len(clip))):
            clip[index] = _scale(clip[index], index / fade_in)
    if fade_out > 0:
        for step in range(1, min(fade_out, len(clip)) + 1):
            position = len(clip) - step
            clip[position] = _scale(clip[position], step / fade_out)

    trimmed = _build_wav(clip, fmt)
    return trimmed, {
        **info,
        "duration": round(frames / rate, 3),
        "start": round(start, 3),
        "end": round(start + frames / rate, 3),
        "size": len(trimmed),
        "trimmed": True,
    }


def wav_peaks(payload: bytes, buckets: int = 160) -> list[float]:
    """Waveform 0..1 for the panel preview (does not change the file)."""
    fmt, _data = _read_chunks(payload)
    buckets = max(8, min(int(buckets), 1200))
    samples = _decode_samples(fmt)
    if not samples:
        return [0.0] * buckets
    step = max(1, len(samples) // buckets)
    peaks: list[float] = []
    for index in range(0, len(samples), step):
        window = samples[index:index + step]
        if not window:
            break
        peaks.append(max(abs(value) for value in window))
    if not peaks:
        return [0.0] * buckets
    loudest = max(peaks) or 1
    peaks = [round(min(1.0, value / loudest), 3) for value in peaks]
    return peaks[:buckets]


def wav_from_bytes(payload: bytes) -> bytes:
    """Rewrites WAV as 16-bit PCM (used when normalising the save)."""
    fmt, _data = _read_chunks(payload)
    samples = _decode_samples(fmt)
    scale = 32767 / max(1, (2 ** (fmt["bits"] - 1)) - 1) if fmt["format"] != _FLOAT else 32767
    normalized = array("i", [int(round(value * scale)) for value in samples])
    return _build_wav(normalized, {**fmt, "bits": 16})
