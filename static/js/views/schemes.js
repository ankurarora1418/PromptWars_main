// Schemes: rule-based eligibility with reasons, plus a Gemini explanation on demand.
import { post } from "../api.js";
import { answerBlock, clear, el, showError, showLoading, withBusy } from "../dom.js";
import { t } from "../i18n.js";
import { navigate } from "../router.js";
import { getProfile } from "../store.js";

const STATUS_LABEL = { eligible: "statusEligible", next_step: "statusNextStep", not_eligible: "statusNotEligible" };
const GROUP_LABEL = { eligible: "groupEligible", next_step: "groupNextStep", not_eligible: "groupNotEligible" };

async function explain(scheme, button, slot) {
  showLoading(slot);
  await withBusy(button, async () => {
    try {
      const data = await post("/api/schemes/explain", { profile: getProfile(), scheme_id: scheme.id });
      clear(slot).append(answerBlock(data.answer));
    } catch (error) {
      showError(slot, error);
    }
  });
}

function schemeCard(scheme) {
  const slot = el("div", { attrs: { "aria-live": "polite" } });
  const explainButton = el("button", { class: "btn btn-primary", attrs: { type: "button" }, text: t("explainMine") });
  explainButton.addEventListener("click", () => explain(scheme, explainButton, slot));
  const actions = [explainButton];
  if (scheme.status !== "not_eligible") {
    actions.push(
      el("button", {
        class: "btn btn-quiet",
        attrs: { type: "button" },
        text: t("docsNeeded"),
        on: { click: () => navigate("documents", { scheme_id: scheme.id }) },
      }),
    );
  }
  if (scheme.next_step === "scheme:eshram") {
    actions.push(
      el("button", {
        class: "btn btn-secondary",
        attrs: { type: "button" },
        text: t("registerEshramFirst"),
        on: { click: () => focusScheme("eshram", true) },
      }),
    );
  }
  return el(
    "article",
    { class: "scheme", attrs: { id: `scheme-${scheme.id}`, tabindex: "-1", "aria-labelledby": `scheme-title-${scheme.id}` } },
    el("span", { class: `status status-${scheme.status}`, text: t(STATUS_LABEL[scheme.status]) }),
    el("h3", { attrs: { id: `scheme-title-${scheme.id}` }, text: scheme.name }),
    el("p", { text: scheme.summary }),
    el("p", {}, el("strong", { text: `${t("youGet")}: ` }), scheme.benefit),
    el("p", {}, el("strong", { text: `${t("cost")}: ` }), scheme.cost),
    scheme.reasons.length ? el("ul", { class: "reasons" }, ...scheme.reasons.map((r) => el("li", { text: r }))) : null,
    el("div", { class: "btn-row" }, ...actions),
    slot,
  );
}

function focusScheme(id, autoExplain = false) {
  const card = document.getElementById(`scheme-${id}`);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  card.focus({ preventScroll: true });
  if (autoExplain) card.querySelector(".btn-primary")?.click();
}

async function load(params) {
  const result = document.getElementById("schemes-result");
  showLoading(result);
  try {
    const data = await post("/api/schemes/match", { profile: getProfile() });
    clear(result);
    for (const status of ["eligible", "next_step", "not_eligible"]) {
      const group = data.schemes.filter((s) => s.status === status);
      if (!group.length) continue;
      result.append(el("h2", { class: "scheme-group-title", text: t(GROUP_LABEL[status]) }), ...group.map(schemeCard));
    }
    if (params.scheme_id) focusScheme(params.scheme_id, true);
  } catch (error) {
    showError(result, error);
  }
}

export const schemesView = {
  onShow(params) {
    load(params);
  },
};
