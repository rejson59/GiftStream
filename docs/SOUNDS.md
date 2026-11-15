# Sounds: trimming, fading and the local library

GiftStream plays a short alert for LIVE events, so every sound you pick ends up clipped anyway (12 s). Version 0.20.0 lets you decide *which* 12 seconds those are, instead of always taking the beginning of a file.

## Where it lives

**Dźwięki i alerty → Przytnij dźwięk** (bottom of the "Wybrane brzmienie" panel).

1. Load a sound: drag a **WAV** into *Plik WAV do przycięcia*, or press **Przytnij wybrany dźwięk** to take whatever is currently selected in the Studio (including a MyInstants result).
2. The waveform appears. Drag the green handles, drag the highlighted block, or type exact **start/end** values.
3. *Fade in* / *Fade out* (milliseconds) soften the cut so the alert does not start or stop with a click.
4. **▶ Odsłuchaj fragment** plays exactly the selected range with the fade applied.
5. **Zapisz przycięty dźwięk** stores the clip and immediately sets it as the LIVE alert.

Quick picks do the common jobs in one click: *Pierwsze 12 s*, *Pierwsze 8 s*, *Najgłośniejszy fragment* (the loudest 12 s window — handy for music), *Środek utworu*.

## How each format is trimmed

| Format | Decoding | Trimming |
| --- | --- | --- |
| WAV (PCM 8/16/24/32-bit and float32, mono or stereo) | server (`app/audio.py`) | server — exact samples, smallest result |
| MP3, M4A, AAC, OGG, FLAC | browser (`AudioContext.decodeAudioData`) | browser, re-encoded to 16-bit WAV on upload |

There is no ffmpeg dependency: the EXE stays self-contained.

## Library

Every clip you upload or trim is kept in `%LOCALAPPDATA%\GiftStream\uploads\sounds` and listed under *Wgrane pliki*, with size and (for WAV) duration. From there you can **Ustaw** a saved sound or **Przytnij** it again without uploading anything twice. `GET /api/sounds/uploads` returns the same list as JSON.

## Trimming a sound from a link

Browsers cannot read audio bytes from another origin (CORS), so *Przytnij wybrany dźwięk* asks GiftStream to fetch the file first: `POST /api/sounds/fetch`. The download is deliberately strict:

- HTTPS only, no credentials in the URL,
- hostname must not be localhost, `.local`, `.internal` or a private/loopback/link-local IP,
- redirects are re-checked with the same rules (a public link cannot bounce to `127.0.0.1`),
- max 10 MB, and the bytes must match the audio container we expect.

Failed downloads never replace the currently selected sound.

## Limits worth knowing

- Alerts stay capped at 12 seconds; a longer selection is cut to 12 s and the panel says so.
- The shortest accepted fragment is 0.05 s.
- Uploads are capped at 10 MB and limited to MP3, WAV, OGG, M4A, AAC and FLAC.
- No YouTube downloads, no full songs from a stream: pick fragments you have the rights to use.
