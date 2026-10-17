// Complaint drafting. Personal details are filled into the letter on the phone only.
import { post } from "../api.js";
import { clear, copyButton, el, renderText, showError, showLoading, speakButton, toast, todayISO, validateForm, withBusy } from "../dom.js";
import { t } from "../i18n.js";
import { getPersonal, getProfile, savePersonal } from "../store.js";

function fillPlaceholders(text, personal) {
  return text
    .replaceAll("[YOUR NAME]", personal.name || "[YOUR NAME]")
    .replaceAll("[YOUR PHONE]", personal.phone || "[YOUR PHONE]")
    .replaceAll("[YOUR WORKER ID]", personal.worker_id || "[YOUR WORKER ID]");
}

function downloadText(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const link = el("a", { attrs: { href: url, download: filename } });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function letterBlock(text, lang, index) {
  const actions = [speakButton(() => text, lang), copyButton(() => text)];
  if (navigator.share) {
    actions.push(
      el("button", {
        class: "btn btn-quiet",
        attrs: { type: "button" },
        text: t("share"),
        on: { click: () => navigator.share({ text }).catch(() => {}) },
      }),
    );
  }
  actions.push(
    el("button", {
      class: "btn btn-quiet",
      attrs: { type: "button" },
      text: t("download"),
      on: { click: () => downloadText(text, `complaint-${index + 1}.txt`) },
    }),
  );
  return el("div", { class: "answer" }, el("div", { class: "letter", attrs: { lang } }, text), el("div", { class: "answer-meta" }, ...actions));
}

function render(data) {
  const personal = getPersonal();
  const text = fillPlaceholders(data.draft.text, personal);
  const parts = text.split(/\n\s*---\s*\n/).filter((p) => p.trim());
  const langs = parts.length > 1 ? [data.draft.language, "en"] : [data.draft.language];
  const where = data.where_to_file;
  return [
    el("h2", { text: t("letterFor") }),
    ...parts.map((part, i) => letterBlock(part.trim(), langs[i] || "en", i)),
    el("p", { class: "source-tag", text: data.draft.source === "gemini" ? t("sourceGemini") : t("sourceOffline") }),
    el(
      "div",
      { class: "panel" },
      el("h2", { text: t("whereToSend") }),
      el("ol", {}, ...where.file_with.map((item) => el("li", { text: item }))),
      where.helplines.length
        ? el(
            "ul",
            { class: "helplines" },
            ...where.helplines.map((h) =>
              el("li", {}, el("a", { attrs: { href: `tel:${h.number}` } }, el("strong", { text: h.number }), el("span", { text: h.name }))),
            ),
          )
        : null,
      el("p", { class: "hint", text: t("notLegalAdvice") }),
    ),
  ];
}

async function submit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const result = document.getElementById("grievance-result");
  if (!validateForm(form, document.getElementById("grievance-error"))) return;
  const data = new FormData(form);
  savePersonal({ name: data.get("name").trim(), phone: data.get("phone").trim(), worker_id: data.get("worker_id").trim() });
  const payload = {
    profile: getProfile(),
    issue_type: data.get("issue_type"),
    against: data.get("against").trim(),
    description: data.get("description").trim(),
    evidence: data.get("evidence").split("\n").map((line) => line.trim()).filter(Boolean).slice(0, 10),
  };
  if (data.get("incident_date")) payload.incident_date = data.get("incident_date");
  if (data.get("amount")) payload.amount = Number(data.get("amount"));
  showLoading(result);
  await withBusy(form.querySelector('button[type="submit"]'), async () => {
    try {
      const response = await post("/api/grievance/draft", payload);
      clear(result).append(...render(response));
      result.querySelector("h2")?.setAttribute("tabindex", "-1");
      result.querySelector("h2")?.focus();
    } catch (error) {
      showError(result, error);
    }
  });
}

export const grievanceView = {
  init(issueTypes) {
    this.setIssueTypes(issueTypes);
    const form = document.getElementById("grievance-form");
    form.incident_date.max = todayISO();
    const personal = getPersonal();
    form.name.value = personal.name;
    form.phone.value = personal.phone;
    form.worker_id.value = personal.worker_id;
    form.addEventListener("submit", submit);
  },
  setIssueTypes(issueTypes) {
    const select = document.getElementById("g-type");
    const selected = select.value;
    select.replaceChildren(...issueTypes.map((item) => new Option(item.label, item.id)));
    if (selected) select.value = selected;
  },
  onShow(params) {
    const form = document.getElementById("grievance-form");
    if (params.issue_type) form.issue_type.value = params.issue_type;
    if (params.amount) form.amount.value = Math.round(params.amount);
    if (params.issue_type) {
      toast(t("draftComplaint"));
      form.against.focus();
    }
  },
};
