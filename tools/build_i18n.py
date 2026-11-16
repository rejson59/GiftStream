"""Build the interface translation catalog and the runtime translator.

Every user-visible string in the dashboard lives in this catalog exactly once.
The English text in `web/index.html`, `web/app.js`, `web/overlay.js` and
`web/sounds.js` is the source of truth; `web/i18n.pl.json` holds the Polish text
for the same key, and `web/i18n.js` is generated from both. The panel rewrites
the page in place, so switching the language can never leave a half-translated
screen behind.

Run ``python tools/build_i18n.py`` after adding or changing a user-visible
string. ``tests/test_i18n.py`` fails when a string has no Polish translation, so
a new label cannot silently ship in English only.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SOURCE_FILES = ["index.html", "overlay.html", "app.js", "overlay.js", "sounds.js"]
CATALOG = WEB / "i18n.pl.json"
OUTPUT = WEB / "i18n.js"

TRANSLATABLE_ATTRS = ("placeholder", "title", "aria-label", "alt")
_ATTR_RE = re.compile(r"\b(" + "|".join(TRANSLATABLE_ATTRS) + r')="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")
_JS_STRING_RE = re.compile(r"'((?:[^'\\\n]|\\.){2,400})'|\"((?:[^\"\\\n]|\\.){2,400})\"")
_TEMPLATE_RE = re.compile(r"`([^`]{2,4000})`")
_TEMPLATE_STATIC_RE = re.compile(r"\$\{[^}]*\}")
_SKIP = re.compile(r"https?:|/api/|/static/|\.(?:js|css|png|svg|json|wav|mp3)\b")
_CODE_PUNCT = re.compile(r"[{}<>=$|`\\;\[\]/]")
# Only code punctuation disqualifies a string; labels legitimately use "&", "(", "/".
_PROSE_PUNCT = re.compile(r"[{}<>=$|`\\\[\]\"']")

# Strings that are markup, protocol, product or song names — never translated.
_CODE_WORDS = {
    "Content-Type", "Escape", "RIFF", "WAVEfmt", "POST", "GET", "System", "TikTokLive",
    "dev", "localhost:25565", '{"count":1}', "GiftStream", "GIFTSTREAM",
    # TikTok gift names are product names.
    "Rose", "Donut", "Doughnut", "Ice Cream", "Finger Heart", "Panda", "Lion",
    "Dragon", "Castle", "Galaxy", "TikTok Universe", "Corgi", "Sunglasses",
    "Money Gun", "Hat and Mustache", "Hand Hearts", "Mike", "Creeper",
    # Song titles in the sound studio.
    "Amor Na Praia", "Atmostra", "Funk Mandala", "Heaven Jumpstyle",
    "Motagem Alquimina", "No Er Amor", "Thrillum Hardtek", "Where Have You Been",
    "X-Cool Ultra Slowed", "Timeless",
}
# Language names stay in their own language in the selector.
_SELF_NAMED = {"English", "Polski", "Polish", "English (UK)", "English (US)"}


def _clean(text: str) -> str:
    # The DOM exposes decoded text, so keys are compared unescaped ("&amp;" -> "&").
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _wanted(text: str) -> bool:
    if len(text) < 3 or _SKIP.search(text):
        return False
    if text in _CODE_WORDS or text in _SELF_NAMED:
        return False
    if text.startswith(("#", ".", "[", ":", "'", '"', ";", ")", "}")) or text.startswith("&"):
        return False
    if not (text[0].isupper() or not text[0].isalnum()):
        return False
    if not re.search(r"[A-Za-z]{3,}", text):
        return False
    if _PROSE_PUNCT.search(text) or "&amp;" in text or "&nbsp;" in text:
        return False
    # Prose (two or more words) or a single label such as "Lightning" / "LANGUAGE".
    return bool(re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", text)
                or re.fullmatch(r"[A-Z][a-z]{2,}[.!]?|[A-Z]{2,}[.!]?", text))


def _wanted_fragment(text: str) -> bool:
    if len(text) < 3 or _SKIP.search(text) or _PROSE_PUNCT.search(text):
        return False
    if text in _CODE_WORDS or text in _SELF_NAMED:
        return False
    return bool(re.search(r"[a-z]{2,}\s+[a-z]{2,}", text))


def html_keys() -> set[str]:
    keys: set[str] = set()
    for name in [f for f in SOURCE_FILES if f.endswith(".html")]:
        keys |= _html_file_keys(name)
    return keys


def _html_file_keys(name: str) -> set[str]:
    source = (WEB / name).read_text(encoding="utf-8")
    keys: set[str] = set()
    for raw in _TAG_RE.split(source):
        text = _clean(raw)
        # A heading split by <br> or <em> keeps its lowercase tail as its own node.
        if _wanted(text) or _wanted_fragment(text):
            keys.add(text)
    # Sentences split by an inline element keep each fragment translatable.
    for value in re.findall(r'data-i18n-continue="([^"]+)"', source):
        text = _clean(value)
        if _wanted(text):
            keys.add(text)
    for _attr, value in _ATTR_RE.findall(source):
        text = _clean(value)
        if _wanted(text):
            keys.add(text)
    return keys


def js_keys() -> set[str]:
    keys: set[str] = set()
    for name in SOURCE_FILES:
        if not name.endswith(".js"):
            continue
        source = (WEB / name).read_text(encoding="utf-8")
        for single, double in _JS_STRING_RE.findall(source):
            text = _clean((single or double).replace("\\'", "'"))
            if _wanted(text):
                keys.add(text)
        # Template literals: only their static parts reach the DOM as plain text.
        for template in _TEMPLATE_RE.findall(source):
            for piece in _TEMPLATE_STATIC_RE.split(template):
                text = _clean(piece)
                if _wanted(text) or _wanted_fragment(text):
                    keys.add(text)
    return keys


def collected_keys() -> list[str]:
    return sorted(html_keys() | js_keys(), key=str.casefold)


def load_catalog() -> dict[str, str]:
    if not CATALOG.exists():
        return {}
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def build() -> tuple[int, str]:
    keys = collected_keys()
    catalog = load_catalog()
    missing = [key for key in keys if key not in catalog]
    # Every catalog entry ships: the server sends its own messages (toasts, API
    # errors) through the same translate() path, so one table covers the whole UI.
    translated = {key: catalog[key] for key in sorted(catalog, key=str.casefold)}
    body = json.dumps(translated, ensure_ascii=False, indent=1)
    OUTPUT.write_text(
        "/* GiftStream interface language — generated by tools/build_i18n.py.\n"
        " * Do not edit by hand: add the Polish text to web/i18n.pl.json and rebuild.\n"
        " */\n"
        "(() => {\n"
        "const STORAGE_KEY = 'giftstream-language';\n"
        f"const PL = {body};\n" + RUNTIME + "})();\n",
        encoding="utf-8",
    )
    return len(translated), "\n".join(missing)


RUNTIME = r"""
const textOriginals = new Map();
const attrOriginals = new Map();
const ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];
let current = 'en';

function storedLang() {
  const query = new URLSearchParams(location.search).get('lang');
  if (query === 'pl' || query === 'en') return query;
  return localStorage.getItem(STORAGE_KEY) === 'pl' ? 'pl' : 'en';
}

function translateText(text) {
  const match = /^(\s*)(.*?)(\s*)$/s.exec(text);
  if (!match) return text;
  const lead = match[1], body = match[2], tail = match[3];
  const polish = PL[body];
  return polish === undefined ? text : lead + polish + tail;
}

function translateElement(element) {
  for (const attr of ATTRS) {
    if (!element.hasAttribute || !element.hasAttribute(attr)) continue;
    let store = attrOriginals.get(element);
    if (!store) { store = {}; attrOriginals.set(element, store); }
    if (store[attr] === undefined) store[attr] = element.getAttribute(attr);
    const original = store[attr];
    const polish = PL[original.trim()];
    element.setAttribute(attr, current === 'pl' && polish !== undefined ? polish : original);
  }
}

function translateNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    if (!textOriginals.has(node)) textOriginals.set(node, node.nodeValue);
    const original = textOriginals.get(node);
    const next = current === 'pl' ? translateText(original) : original;
    if (node.nodeValue !== next) node.nodeValue = next;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  if (node.tagName === 'SCRIPT' || node.tagName === 'STYLE') return;
  translateElement(node);
  for (const child of node.childNodes) translateNode(child);
}

function apply(root = document.body) {
  current = storedLang();
  document.documentElement.lang = current;
  if (root) translateNode(root);
  return root;
}

function translate(text, variables) {
  current = storedLang();
  const key = String(text);
  let out = current === 'pl' && PL[key] !== undefined ? PL[key] : key;
  if (variables) for (const [name, value] of Object.entries(variables)) out = out.split(`{${name}}`).join(String(value));
  return out;
}

const pending = new Set();
function schedule(node) {
  if (current !== 'pl' || !node) return;
  pending.add(node);
  if (pending.size > 1) return;
  queueMicrotask(() => {
    for (const item of pending) {
      try { if (item.isConnected) translateNode(item); } catch (error) { /* stale node */ }
    }
    pending.clear();
  });
}

const observer = new MutationObserver((records) => {
  if (current !== 'pl') return;
  for (const record of records) {
    if (record.type === 'characterData') schedule(record.target);
    else if (record.type === 'attributes') schedule(record.target);
    else for (const node of record.addedNodes) schedule(node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode);
  }
});

window.GiftStreamI18n = {
  getLang: () => storedLang(),
  setLang(lang) {
    localStorage.setItem(STORAGE_KEY, lang === 'pl' ? 'pl' : 'en');
    apply();
    window.dispatchEvent(new CustomEvent('giftstream-language-change', { detail: { language: storedLang() } }));
  },
  translate,
  apply,
  t: (text) => translate(text),
};

apply();
observer.observe(document.body, {
  subtree: true, childList: true, characterData: true,
  attributes: true, attributeFilter: ATTRS,
});
"""


if __name__ == "__main__":
    done, missing = build()
    print(f"catalog: {done} translated")
    if missing:
        print("missing Polish translations:")
        for key in missing.splitlines():
            print("  ", key)


POLISH_WORDS = re.compile(
    r"\b(?:nie|się|jest|tylko|który|aby|oraz|przez|dla|już|może|będzie|lub|albo|gdy|"
    r"plik|katalog|sprawdzanie|pobieram|ustawienia|zapisano|usunięto|wybrano|pulpit|"
    r"integracje|kopiuj|anuluj|pracownia|zdarzenie|polubienia|wersja|poziom|gracz|"
    r"serwer|mapa|dźwięk|prezent|wybierz|usuń|dodaj|wróć|więcej|mniej|wszystkie|gotowe|"
    r"sprawdź|uruchom|zatrzymaj|pobierz|zainstaluj|połącz|rozłącz|kanał|nazwa|widzowie|"
    r"monety|diamenty|czas|dzień|noc|edytuj|zapisz|włącz|wyłącz)\b",
    re.IGNORECASE,
)
POLISH_DIACRITICS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")


def polish_leftovers() -> list[str]:
    """English source files must not contain Polish text — only the catalog may."""
    findings: list[str] = []
    for name in SOURCE_FILES:
        source = (WEB / name).read_text(encoding="utf-8")
        for match in POLISH_DIACRITICS.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            findings.append(f"{name}:{line}: {source[max(0, match.start() - 40):match.start() + 20]!r}")
    return findings
