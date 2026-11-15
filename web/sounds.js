/* GiftStream — Studio dźwięków: przycinanie, fade, podgląd fali, biblioteka plików.
   Wydzielone z app.js, bo obsługa audio ma własny stan (bufor, zaznaczenie, playery). */
(function () {
  'use strict';

  // Zgodne z serwerowym limitem (app/audio.py); różnica tylko na wypadek zmiany jednej strony.
  const MAX_CLIP_SECONDS = 12;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));
  const $id = (id) => document.getElementById(id);

  const trim = {
    buffer: null,        // AudioBuffer oryginału (mp3/wav/…)
    wavBlob: null,       // oryginalny plik WAV, gdy mamy go bez dekodowania
    name: '',
    duration: 0,
    start: 0,
    end: 0,
    peaks: [],
    busy: false,
    notice: '',      // komunikat po zapisie/błędzie — nie może zniknąć przy odświeżeniu pól
  };

  let audioContext = null;
  const context = () => {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    if (!audioContext || audioContext.state === 'closed') audioContext = new Ctor();
    if (audioContext.state === 'suspended') audioContext.resume().catch(() => {});
    return audioContext;
  };

  const setStatus = (text) => {
    const node = $id('trim-status');
    if (node) node.textContent = text || '';
  };

  const fmt = (seconds) => `${clamp(seconds, 0, 86400).toFixed(2)} s`;

  /* -- podgląd fali ------------------------------------------------------ */

  function peaksFromBuffer(buffer, buckets = 180) {
    const channel = buffer.getChannelData(0);
    const step = Math.max(1, Math.floor(channel.length / buckets));
    const peaks = [];
    for (let index = 0; index < channel.length; index += step) {
      let peak = 0;
      for (let probe = 0; probe < step && index + probe < channel.length; probe += 4) {
        const value = Math.abs(channel[index + probe]);
        if (value > peak) peak = value;
      }
      peaks.push(peak);
    }
    const loudest = Math.max(...peaks, 0.0001);
    return peaks.map((value) => value / loudest);
  }

  function drawWave() {
    const canvas = $id('trim-wave');
    if (!canvas) return;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 720;
    const height = 96;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--lime').trim() || '#c3f53c';
    ctx.fillStyle = 'rgba(255,255,255,.05)';
    ctx.fillRect(0, 0, width, height);
    const peaks = trim.peaks;
    if (!peaks.length || !trim.duration) return;
    const middle = height / 2;
    const barWidth = width / peaks.length;
    const startX = (trim.start / trim.duration) * width;
    const endX = (trim.end / trim.duration) * width;
    peaks.forEach((peak, index) => {
      const x = index * barWidth;
      const barHeight = Math.max(1, peak * (height - 8));
      const inside = x >= startX && x + barWidth <= endX;
      ctx.fillStyle = inside ? accent : 'rgba(255,255,255,.22)';
      ctx.fillRect(x, middle - barHeight / 2, Math.max(1, barWidth - 0.6), barHeight);
    });
    updateSelectionBox();
  }

  function updateSelectionBox() {
    const box = $id('trim-selection');
    if (!box || !trim.duration) return;
    box.style.left = `${(trim.start / trim.duration) * 100}%`;
    box.style.width = `${Math.max(0.4, ((trim.end - trim.start) / trim.duration) * 100)}%`;
    const empty = $id('trim-empty');
    if (empty) empty.hidden = true;
    const range = $id('trim-range');
    if (range) range.hidden = false;
  }

  function syncFields() {
    const start = $id('trim-start');
    const end = $id('trim-end');
    if (start) { start.max = trim.duration || 0; start.value = trim.start.toFixed(2); }
    if (end) { end.max = trim.duration || 0; end.value = trim.end.toFixed(2); }
    const over = trim.end - trim.start > MAX_CLIP_SECONDS + 0.001;
    const summary = trim.buffer
      ? `Fragment ${fmt(trim.start)} – ${fmt(trim.end)} (${fmt(trim.end - trim.start)}).${over ? ' Dłuższy niż 12 s — zostanie ucięty.' : ''}`
      : 'Dźwięk czeka na wybór.';
    setStatus(trim.notice ? `${summary} ${trim.notice}` : summary);
    const apply = $id('trim-apply');
    const preview = $id('trim-preview');
    const ready = !!trim.buffer && trim.end - trim.start >= 0.05;
    if (apply) apply.disabled = !ready || trim.busy;
    if (preview) preview.disabled = !ready;
    drawWave();
  }

  /* -- wczytywanie dźwięku ---------------------------------------------- */

  async function decode(arrayBuffer) {
    const ctx = context();
    if (!ctx) throw new Error('Ta przeglądarka nie obsługuje odtwarzania i przycinania dźwięku.');
    return new Promise((resolve, reject) => {
      // Starsze Safari wymaga wersji z callbackami.
      const fallback = ctx.decodeAudioData(arrayBuffer, resolve, reject);
      if (fallback && typeof fallback.then === 'function') fallback.then(resolve).catch(reject);
    });
  }

  function applyBuffer(buffer, name) {
    trim.buffer = buffer;
    trim.name = name || 'dźwięk';
    trim.duration = Math.max(0.05, buffer.duration);
    trim.start = 0;
    trim.end = Math.min(trim.duration, MAX_CLIP_SECONDS);
    trim.peaks = peaksFromBuffer(buffer);
    const stage = $id('trim-stage');
    if (stage) stage.classList.add('has-audio');
    for (const id of ['trim-start', 'trim-end']) if ($id(id)) $id(id).disabled = false;
    syncFields();
  }

  async function loadBlob(blob, name) {
    trim.busy = true;
    trim.notice = '';
    setStatus('Odczytywuję dźwięk…');
    try {
      const data = await blob.arrayBuffer();
      const buffer = await decode(data.slice(0));
      applyBuffer(buffer, name);
      trim.wavBlob = /\.wav$/i.test(name || '') || blob.type === 'audio/wav' ? blob : null;
      setStatus(`Wczytano ${name || 'dźwięk'} — ${fmt(trim.duration)}.`);
    } catch (error) {
      setStatus(`Nie udało się odczytać tego pliku: ${error.message || error}. Spróbuj WAV albo MP3.`);
    } finally {
      trim.busy = false;
      syncFields();
    }
  }

  async function loadUrl(url, name) {
    setStatus('Pobieram dźwięk do przycięcia…');
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Nie udało się pobrać pliku (${response.status}).`);
    const blob = await response.blob();
    await loadBlob(blob, name || url.split('/').pop() || 'dźwięk');
  }

  async function loadFromSelected() {
    const config = window.GiftStream?.state?.liveConfig || {};
    const url = (config.sound_url || '').trim();
    if (!url) {
      setStatus('Najpierw wybierz dźwięk w Studio albo wgraj plik WAV powyżej.');
      return;
    }
    $id('trim-from-selected').disabled = true;
    try {
      if (url.startsWith('/api/sounds/uploads/')) {
        await loadUrl(url, config.sound_label || url.split('/').pop());
        return;
      }
      // Obcy serwer: przeglądarka nie odczyta bajtów (CORS), więc pobiera GiftStream.
      const fetched = await window.GiftStream.api('/api/sounds/fetch', {
        method: 'POST',
        body: JSON.stringify({ url, name: config.sound_label || '' }),
      });
      await loadUrl(fetched.url, fetched.name);
      setStatus(`Pobrano „${fetched.name}” (${fmt(trim.duration)}) — wybierz fragment.`);
    } catch (error) {
      setStatus(error.message || 'Nie udało się przygotować dźwięku do przycięcia.');
    } finally {
      $id('trim-from-selected').disabled = false;
    }
  }

  /* -- zaznaczanie zakresu ---------------------------------------------- */

  function setRange(start, end) {
    if (!trim.duration) return;
    trim.start = clamp(start, 0, Math.max(0, trim.duration - 0.05));
    trim.end = clamp(end, trim.start + 0.05, trim.duration);
    syncFields();
  }

  function quickPick(kind) {
    if (!trim.duration) return;
    if (kind === 'peak') {
      const bucket = Math.max(0.05, trim.peaks.length ? trim.duration / trim.peaks.length : trim.duration);
      let bestIndex = 0;
      let bestScore = -1;
      const windowSize = Math.max(1, Math.round(MAX_CLIP_SECONDS / bucket));
      trim.peaks.forEach((peak, index) => {
        let sum = 0;
        for (let probe = index; probe < Math.min(trim.peaks.length, index + windowSize); probe += 1) sum += trim.peaks[probe];
        if (sum > bestScore) { bestScore = sum; bestIndex = index; }
      });
      const start = bestIndex * bucket;
      setRange(start, start + MAX_CLIP_SECONDS);
      return;
    }
    if (kind === 'center') {
      const length = Math.min(MAX_CLIP_SECONDS, trim.duration);
      const start = Math.max(0, (trim.duration - length) / 2);
      setRange(start, start + length);
      return;
    }
    setRange(0, Math.min(Number(kind) || MAX_CLIP_SECONDS, trim.duration));
  }

  function bindRangeDrag() {
    const stage = $id('trim-stage');
    const range = $id('trim-range');
    if (!stage || !range) return;
    let mode = null;

    const positionToTime = (event) => {
      const rect = stage.getBoundingClientRect();
      const ratio = clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 1);
      return ratio * trim.duration;
    };

    const onMove = (event) => {
      if (!mode || !trim.duration) return;
      const time = positionToTime(event);
      if (mode === 'start') setRange(Math.min(time, trim.end - 0.05), trim.end);
      else if (mode === 'end') setRange(trim.start, Math.max(time, trim.start + 0.05));
      else if (mode === 'move' && dragOffset != null) {
        const length = trim.end - trim.start;
        const start = clamp(time - dragOffset, 0, Math.max(0, trim.duration - length));
        setRange(start, start + length);
      }
      event.preventDefault();
    };
    let dragOffset = null;

    const stop = () => {
      mode = null;
      dragOffset = null;
      document.body.classList.remove('trim-dragging');
    };

    document.querySelectorAll('[data-trim-handle]').forEach((handle) => {
      handle.addEventListener('pointerdown', (event) => {
        if (!trim.duration) return;
        mode = handle.dataset.trimHandle;
        document.body.classList.add('trim-dragging');
        event.preventDefault();
      });
    });

    const box = $id('trim-selection');
    if (box) {
      box.addEventListener('pointerdown', (event) => {
        if (!trim.duration) return;
        mode = 'move';
        dragOffset = positionToTime(event) - trim.start;
        document.body.classList.add('trim-dragging');
        event.preventDefault();
      });
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  }

  /* -- odsłuch i zapis --------------------------------------------------- */

  let previewSource = null;

  function stopPreview() {
    if (previewSource) {
      try { previewSource.stop(); } catch { /* już zatrzymane */ }
      previewSource = null;
    }
  }

  function previewRange() {
    const ctx = context();
    if (!ctx || !trim.buffer) return;
    stopPreview();
    const length = Math.min(trim.end - trim.start, MAX_CLIP_SECONDS);
    const source = ctx.createBufferSource();
    source.buffer = trim.buffer;
    const gain = ctx.createGain();
    const volume = Number(window.GiftStream?.state?.liveConfig?.sound_volume);
    gain.gain.value = clamp(Number.isFinite(volume) ? volume : 0.55, 0, 1);
    const fadeIn = clamp(Number($id('trim-fade-in')?.value) || 0, 0, 2000) / 1000;
    const fadeOut = clamp(Number($id('trim-fade-out')?.value) || 0, 0, 2000) / 1000;
    const now = ctx.currentTime + 0.02;
    gain.gain.setValueAtTime(fadeIn > 0 ? 0 : gain.gain.value, now);
    if (fadeIn > 0) gain.gain.linearRampToValueAtTime(Number.isFinite(volume) ? volume : 0.55, now + Math.min(fadeIn, length));
    if (fadeOut > 0) {
      const at = Math.max(now + Math.min(fadeIn, length), now + length - Math.min(fadeOut, length));
      gain.gain.setValueAtTime(Number.isFinite(volume) ? volume : 0.55, at);
      gain.gain.linearRampToValueAtTime(0, now + length);
    }
    source.connect(gain).connect(ctx.destination);
    source.start(now, trim.start, length);
    source.onended = () => { previewSource = null; };
    previewSource = source;
  }

  function encodeWav(buffer) {
    const channels = Math.min(2, buffer.numberOfChannels);
    const frames = buffer.length;
    const bytes = frames * channels * 2;
    const view = new DataView(new ArrayBuffer(44 + bytes));
    const writeString = (offset, text) => {
      for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + bytes, true);
    writeString(8, 'WAVEfmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, channels, true);
    view.setUint32(24, buffer.sampleRate, true);
    view.setUint32(28, buffer.sampleRate * channels * 2, true);
    view.setUint16(32, channels * 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, bytes, true);
    const data = [];
    for (let channel = 0; channel < channels; channel += 1) data.push(buffer.getChannelData(channel));
    let offset = 44;
    for (let frame = 0; frame < frames; frame += 1) {
      for (let channel = 0; channel < channels; channel += 1) {
        const sample = Math.max(-1, Math.min(1, data[channel][frame] || 0));
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      }
    }
    return new Blob([view], { type: 'audio/wav' });
  }

  function renderTrimmed() {
    const ctx = context();
    const length = Math.min(trim.end - trim.start, MAX_CLIP_SECONDS);
    const frames = Math.max(1, Math.round(length * trim.buffer.sampleRate));
    const result = ctx.createBuffer(Math.min(2, trim.buffer.numberOfChannels), frames, trim.buffer.sampleRate);
    const fadeIn = clamp(Number($id('trim-fade-in')?.value) || 0, 0, 2000) / 1000;
    const fadeOut = clamp(Number($id('trim-fade-out')?.value) || 0, 0, 2000) / 1000;
    for (let channel = 0; channel < result.numberOfChannels; channel += 1) {
      const source = trim.buffer.getChannelData(Math.min(channel, trim.buffer.numberOfChannels - 1));
      const target = result.getChannelData(channel);
      const first = Math.round(trim.start * trim.buffer.sampleRate);
      for (let index = 0; index < frames; index += 1) {
        let gain = 1;
        const seconds = index / trim.buffer.sampleRate;
        if (fadeIn > 0 && seconds < fadeIn) gain = seconds / fadeIn;
        if (fadeOut > 0 && length - seconds < fadeOut) gain = Math.min(gain, (length - seconds) / fadeOut);
        target[index] = (source[first + index] || 0) * Math.max(0, gain);
      }
    }
    return result;
  }

  async function applyTrim() {
    if (!trim.buffer || trim.end - trim.start < 0.05) return;
    const button = $id('trim-apply');
    button.disabled = true;
    setStatus('Zapisuję przycięty dźwięk…');
    try {
      const rendered = renderTrimmed();
      const useServer = trim.wavBlob && trim.end - trim.start <= MAX_CLIP_SECONDS + 0.001;
      let saved;
      if (useServer) {
        // WAV przycinamy na serwerze: dokładniejsze próbki i mniejszy plik wynikowy.
        const query = new URLSearchParams({
          start: trim.start.toFixed(3), end: trim.end.toFixed(3), filename: trim.name,
          fade_in_ms: String(clamp(Number($id('trim-fade-in')?.value) || 0, 0, 2000)),
          fade_out_ms: String(clamp(Number($id('trim-fade-out')?.value) || 0, 0, 2000)),
        });
        const response = await fetch(`/api/sounds/trim?${query}`, {
          method: 'POST', headers: { 'Content-Type': trim.wavBlob.type || 'audio/wav' }, body: trim.wavBlob, cache: 'no-store',
        });
        saved = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(saved.detail || 'Nie udało się przyciąć pliku.');
      } else {
        // MP3/M4A/OGG: przeglądarka dekoduje i wysyła gotowy WAV.
        const blob = encodeWav(rendered);
        const response = await fetch(`/api/sounds/upload?filename=${encodeURIComponent(`${trim.name.replace(/\.[^.]+$/, '')}-fragment.wav`)}`, {
          method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: blob, cache: 'no-store',
        });
        saved = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(saved.detail || 'Nie udało się zapisać przyciętego dźwięku.');
        saved.name = `${trim.name} · ${trim.start.toFixed(2)}–${(trim.start + (trim.end - trim.start)).toFixed(2)} s`;
      }
      trim.notice = `✓ Zapisano ${fmt(saved.duration || (trim.end - trim.start))} i ustawiono jako alert LIVE.`;
      if (window.GiftStream?.selectSoundUrl) await window.GiftStream.selectSoundUrl(saved.url, saved.name);
      await refreshLibrary();
    } catch (error) {
      trim.notice = `✗ ${error.message || 'Nie udało się zapisać przyciętego dźwięku.'}`;
    } finally {
      syncFields();
    }
  }

  /* -- biblioteka plików ------------------------------------------------- */

  async function refreshLibrary() {
    const box = $id('trim-library');
    if (!box) return;
    try {
      const data = await window.GiftStream.api('/api/sounds/uploads');
      const files = data.files || [];
      if (!files.length) {
        box.innerHTML = '<div class="empty-note">Brak wgranych plików. Wgraj plik albo przytnij dźwięk — pojawi się tutaj.</div>';
        return;
      }
      box.innerHTML = files.map((file) => `<div class="trim-library-row">
        <span class="trim-library-mark">♫</span>
        <span class="trim-library-copy"><b>${window.GiftStream.esc(file.name.slice(0, 22))}</b><small>${(Number(file.size) / 1024).toFixed(0)} KB${file.duration != null ? ` · ${fmt(file.duration)}` : ''}</small></span>
        <button type="button" class="tiny-action" data-trim-use="${window.GiftStream.esc(file.url)}">Ustaw</button>
        <button type="button" class="tiny-action" data-trim-edit="${window.GiftStream.esc(file.url)}">Przytnij</button>
      </div>`).join('');
      box.querySelectorAll('[data-trim-use]').forEach((button) => {
        button.onclick = () => window.GiftStream.selectSoundUrl?.(button.dataset.trimUse, '');
      });
      box.querySelectorAll('[data-trim-edit]').forEach((button) => {
        button.onclick = () => loadUrl(button.dataset.trimEdit, button.dataset.trimEdit.split('/').pop()).catch((error) => setStatus(error.message));
      });
    } catch (error) {
      box.innerHTML = `<div class="empty-note">Nie udało się odczytać listy plików: ${window.GiftStream.esc(error.message)}</div>`;
    }
  }

  /* -- start ------------------------------------------------------------- */

  function setup() {
    if (!$id('sound-trimmer') || !window.GiftStream) return;
    $id('trim-file').onchange = (event) => {
      const file = event.target.files?.[0];
      if (file) loadBlob(file, file.name);
    };
    $id('trim-from-selected').onclick = loadFromSelected;
    $id('trim-preview').onclick = previewRange;
    $id('trim-apply').onclick = applyTrim;
    $id('trim-library-refresh').onclick = refreshLibrary;
    $id('trim-start').oninput = () => setRange(Number($id('trim-start').value), trim.end);
    $id('trim-end').oninput = () => setRange(trim.start, Number($id('trim-end').value));
    $id('trim-fade-in').oninput = syncFields;
    $id('trim-fade-out').oninput = syncFields;
    document.querySelectorAll('[data-trim-quick]').forEach((button) => {
      button.onclick = () => quickPick(button.dataset.trimQuick);
    });
    bindRangeDrag();
    window.addEventListener('resize', drawWave);
    refreshLibrary();
    drawWave();
  }

  window.GiftStreamSounds = { setup, refreshLibrary, loadFromSelected, get trim() { return trim; } };
})();
