// Home: context-ranked "Today for you" cards and the free-form Ask box.
import { post } from "../api.js";
import { answerBlock, clear, el, showError, showLoading, withBusy } from "../dom.js";
import { t } from "../i18n.js";
import { navigate } from "../router.js";
import { entriesForApi, getProfile } from "../store.js";
import { openProfile } from "./profile.js";

const SECTION_KEYS = {
  earnings: "navEarnings",
  safety: "navSafety",
  schemes: "navSchemes",
  documents: "navDocuments",
  grievance: "navGrievance",
};

function greeting(hour) {
  if (hour >= 22 || hour < 5) return t("greetingNight");
  if (hour < 12) return t("greetingMorning");
  if (hour < 17) return t("greetingAfternoon");
  return t("greetingEvening");
}

function openModule(module, params) {
  if (module === "profile") openProfile();
  else navigate(module, params);
}

function renderCards(cards) {
  const list = clear(document.getElementById("home-cards"));
  for (const card of cards) {
    const label = card.module === "profile" ? t("profile") : t("openSection", { section: t(SECTION_KEYS[card.module]) });
    list.append(
      el(
        "li",
        { class: `card tone-${card.tone}` },
        el(
          "div",
          { class: "card-body" },
          el("h3", { text: card.title }),
          el("p", { text: card.body }),
          el("button", {
            class: card.tone === "warning" ? "btn btn-secondary" : "btn btn-quiet",
            attrs: { type: "button" },
            text: label,
            on: { click: () => openModule(card.module, card.params) },
          }),
        ),
      ),
    );
  }
}

async function loadCards() {
  const hour = new Date().getHours();
  document.getElementById("home-greeting").textContent = greeting(hour);
  const list = document.getElementById("home-cards");
  showLoading(list);
  try {
    const data = await post("/api/home", { profile: getProfile(), hour, entries: entriesForApi() });
    renderCards(data.cards);
  } catch (error) {
    showError(list, error);
  }
}

async function ask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const input = form.message;
  const result = document.getElementById("ask-result");
  if (!input.value.trim()) {
    input.focus();
    return;
  }
  showLoading(result);
  await withBusy(form.querySelector("button"), async () => {
    try {
      const data = await post("/api/chat", { profile: getProfile(), message: input.value.trim(), entries: entriesForApi() });
      const actions = data.suggested_module
        ? [
            el("button", {
              class: "btn btn-secondary",
              attrs: { type: "button" },
              text: t("openSection", { section: t(SECTION_KEYS[data.suggested_module]) }),
              on: { click: () => navigate(data.suggested_module) },
            }),
          ]
        : [];
      clear(result).append(answerBlock(data.answer, actions));
    } catch (error) {
      showError(result, error);
    }
  });
}

export const homeView = {
  init() {
    document.getElementById("ask-form").addEventListener("submit", ask);
  },
  onShow() {
    loadCards();
  },
};
