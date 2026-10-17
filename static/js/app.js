// App bootstrap: translations, metadata, profile, router and global controls.
import { get } from "./api.js";
import { applyTranslations, hasUiTranslation, loadLanguage, t } from "./i18n.js";
import { currentViewName, registerView, show, startRouter } from "./router.js";
import { getPrefs, getProfile, hasProfile, saveProfile, savePrefs } from "./store.js";
import { stopSpeaking } from "./speech.js";
import { toast } from "./dom.js";
import { documentsView } from "./views/documents.js";
import { earningsView } from "./views/earnings.js";
import { grievanceView } from "./views/grievance.js";
import { homeView } from "./views/home.js";
import { initProfile, openProfile } from "./views/profile.js";
import { safetyView } from "./views/safety.js";
import { schemesView } from "./views/schemes.js";

let meta = null;

async function setLanguage(code, { announce = false } = {}) {
  await loadLanguage(code);
  applyTranslations();
  document.getElementById("lang-select").value = code;
  if (meta) {
    const fresh = await get(`/api/meta?lang=${encodeURIComponent(code)}`);
    grievanceView.setIssueTypes(fresh.issue_types);
  }
  if (announce && !hasUiTranslation(code)) {
    const name = meta?.languages.find((l) => l.code === code)?.name || code;
    toast(t("uiEnglishOnly", { lang: name }));
  }
}

function applyTextSize(large) {
  document.documentElement.classList.toggle("large-text", large);
  document.getElementById("text-size").setAttribute("aria-pressed", String(large));
}

async function checkAi() {
  try {
    const health = await get("/api/health");
    document.getElementById("offline-banner").hidden = health.ai_enabled;
  } catch {
    /* banner stays hidden; individual requests show their own errors */
  }
}

function rerenderCurrent() {
  stopSpeaking();
  // Answers on screen were written in the previous language; clear them.
  ["ask-result", "safety-result", "document-result", "grievance-result"].forEach((id) => {
    document.getElementById(id).replaceChildren();
  });
  show(currentViewName() || "home", { focus: false });
}

async function start() {
  const profile = getProfile();
  await loadLanguage(profile.language);
  meta = await get(`/api/meta?lang=${encodeURIComponent(profile.language)}`);

  const langSelect = document.getElementById("lang-select");
  langSelect.replaceChildren(...meta.languages.map((l) => new Option(l.name, l.code)));
  applyTranslations();
  langSelect.value = profile.language;

  initProfile({
    languages: meta.languages,
    states: meta.states,
    onSave: async (saved) => {
      await setLanguage(saved.language, { announce: true });
      rerenderCurrent();
    },
  });
  homeView.init();
  earningsView.init();
  safetyView.init();
  documentsView.init();
  grievanceView.init(meta.issue_types);

  registerView("home", homeView);
  registerView("earnings", earningsView);
  registerView("safety", safetyView);
  registerView("schemes", schemesView);
  registerView("documents", documentsView);
  registerView("grievance", grievanceView);

  langSelect.addEventListener("change", async () => {
    saveProfile({ language: langSelect.value });
    await setLanguage(langSelect.value, { announce: true });
    rerenderCurrent();
  });

  applyTextSize(getPrefs().largeText);
  document.getElementById("text-size").addEventListener("click", () => {
    const large = !getPrefs().largeText;
    savePrefs({ largeText: large });
    applyTextSize(large);
  });
  document.getElementById("open-profile").addEventListener("click", openProfile);

  startRouter();
  checkAi();
  if (!hasProfile()) openProfile();
}

start().catch(() => {
  const banner = document.getElementById("offline-banner");
  banner.textContent = "Saathi could not start. Check your internet connection and reload the page.";
  banner.hidden = false;
});
