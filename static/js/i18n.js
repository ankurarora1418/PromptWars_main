// UI translations. Menus exist in English and Hindi; other languages fall back to English
// for menus while Gemini answers in the chosen language.

const UI_LANGS = ["en", "hi"];
let english = {};
let current = {};
let uiLang = "en";

async function fetchDict(code) {
  const response = await fetch(`/static/i18n/${code}.json`);
  if (!response.ok) throw new Error(`Missing translations for ${code}`);
  return response.json();
}

export async function loadLanguage(code) {
  if (!Object.keys(english).length) english = await fetchDict("en");
  uiLang = UI_LANGS.includes(code) ? code : "en";
  current = uiLang === "en" ? english : await fetchDict(uiLang);
  document.documentElement.lang = uiLang;
  return uiLang;
}

export function hasUiTranslation(code) {
  return UI_LANGS.includes(code);
}

export function uiLanguage() {
  return uiLang;
}

/** Translate a key, filling {placeholders} from vars. */
export function t(key, vars = {}) {
  const template = current[key] ?? english[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? String(vars[name]) : `{${name}}`));
}

/** Apply translations to every element marked with data-i18n attributes. */
export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nLabel));
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
}
