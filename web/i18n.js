/* GiftStream — interface language.
 *
 * Version 0.21.0 is English-only: the dashboard, the overlays and every
 * in-game message were rewritten in English, so there is no translation table
 * left to apply. This module stays in place because the panel, the overlays and
 * the Sound studio use it to read and store the language code. It keeps the old
 * API (`getLang`, `setLang`, `translate`, `apply`) so nothing else has to change,
 * and it stays a no-op that simply reports `en`.
 */
(() => {
  const LANG = 'en';
  const STORAGE_KEY = 'giftstream-language';

  function getLang() {
    const query = new URLSearchParams(location.search).get('lang');
    if (query === 'en') return LANG;
    // A stored Polish preference from an older release is ignored, not honoured.
    if (localStorage.getItem(STORAGE_KEY) === 'pl') localStorage.setItem(STORAGE_KEY, LANG);
    return LANG;
  }

  function apply(root = document) {
    document.documentElement.lang = LANG;
    return root;
  }

  window.GiftStreamI18n = {
    getLang,
    setLang(lang) {
      localStorage.setItem(STORAGE_KEY, lang === 'pl' ? 'pl' : LANG);
      apply();
      window.dispatchEvent(new CustomEvent('giftstream-language-change', { detail: { language: getLang() } }));
    },
    translate(text) {
      return String(text);
    },
    apply,
  };

  apply();
})();
