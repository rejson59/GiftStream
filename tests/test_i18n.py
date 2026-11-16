"""The interface language must be complete in both directions.

These tests are the reason a new label cannot ship half-translated: the English
source files are scanned, every user-visible string must exist in the Polish
catalog, the runtime table must match the catalog exactly, and neither language
may leak into the other's text.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT / "tools"))

import build_i18n  # noqa: E402  (plain script in tools/)


def catalog() -> dict[str, str]:
    return json.loads((WEB / "i18n.pl.json").read_text(encoding="utf-8"))


def test_every_visible_string_has_a_polish_translation():
    missing = sorted(set(build_i18n.collected_keys()) - set(catalog()))
    assert missing == [], f"Add the Polish text to web/i18n.pl.json: {missing}"


def test_no_english_leftovers_in_the_polish_translation():
    """A Polish string must not be a copy of the English one unless it is a name."""
    # Product names, brands and technical tokens stay identical in both languages.
    names = set(build_i18n._CODE_WORDS) | {
        "LIVE", "LIVE Arena", "Minecraft", "PLN", "DEV", "UTC", "PUT", "CHAOS", "Disco",
        "Disco!", "Fragment", "Launcher Minecraft Java", "Level", "Online:",
        "Parkour: sprint · 8 s", "START · S", "TikTok LIVE",
        "Niekompletny fragment aktualizacji.",
        "Podaj poprawny @username TikTok LIVE (bez spacji).",
    }
    copied = [key for key, value in catalog().items() if value.strip() == key.strip() and key not in names]
    assert copied == [], f"Untranslated entries: {copied}"


def test_no_polish_leftovers_in_the_english_sources():
    assert build_i18n.polish_leftovers() == []


def test_the_runtime_table_matches_the_catalog():
    runtime = (WEB / "i18n.js").read_text(encoding="utf-8")
    build_i18n.build()
    rebuilt = (WEB / "i18n.js").read_text(encoding="utf-8")
    assert runtime == rebuilt, "web/i18n.js is stale — run python tools/build_i18n.py"
    assert len(json.loads(re.search(r"const PL = (\{.*?\});\n", runtime, re.S).group(1))) == len(catalog())


def test_server_messages_used_by_the_panel_have_a_translation():
    """Toasts and API errors are English strings from the backend."""
    sys.path.insert(0, str(ROOT / "tests"))
    import ast
    import re as _re

    files = ["main.py", "parkour_server.py", "updater.py", "gifts.py", "myinstants.py", "audio.py",
             "bridge.py", "presets.py", "earnings.py", "tiktok_connector.py", "models.py", "games.py",
             "desktop.py"]
    messages = set()
    for name in files:
        tree = ast.parse((ROOT / "app" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                func_name = getattr(func, "id", None) or getattr(func, "attr", None)
                if func_name in ("HTTPException", "RuntimeError", "ValueError", "UpdateError"):
                    for arg in node.args[:2]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            messages.add(arg.value.strip())
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                value = node.value.value.strip()
                if 5 < len(value) < 260 and value[:1].isupper():
                    messages.add(value)
    known = set(catalog())
    missing = sorted(message for message in messages
                     if _re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", message) and message not in known)
    assert missing == [], f"Server messages without Polish text: {missing}"


def test_the_language_switcher_offers_both_languages():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<option value="en">English</option>' in page
    assert '<option value="pl">Polski</option>' in page
    assert 'id="language-select"' in page


def test_the_translator_rewrites_text_and_restores_english():
    """A quick sanity check of the runtime translation rules in JavaScript."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not available")
    script = """
    const store = {};
    global.Node = {TEXT_NODE: 3, ELEMENT_NODE: 1};
    global.localStorage = {getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v; }};
    global.location = {search: ''};
    global.document = {
      body: {childNodes: []}, documentElement: {lang: 'en'},
      addEventListener() {}, dispatchEvent() {},
    };
    global.window = {addEventListener() {}, dispatchEvent() {}};
    global.queueMicrotask = fn => fn();
    global.MutationObserver = class { observe() {} };
    require('""" + str(WEB / "i18n.js") + """');
    localStorage.setItem('giftstream-language', 'pl');
    console.log(window.GiftStreamI18n.t('Dashboard') + '|' + window.GiftStreamI18n.t('Next level'));
    localStorage.setItem('giftstream-language', 'en');
    console.log(window.GiftStreamI18n.t('Dashboard') + '|' + window.GiftStreamI18n.t('Unknown string'));
    """
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["Pulpit|Następny level", "Dashboard|Unknown string"]
