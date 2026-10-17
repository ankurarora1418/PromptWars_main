// Safety: one-tap emergency numbers and tips tuned to work type, time and weather.
import { post } from "../api.js";
import { answerBlock, clear, el, showError, showLoading, withBusy } from "../dom.js";
import { t } from "../i18n.js";
import { getProfile } from "../store.js";

function renderHelplines(helplines) {
  const list = clear(document.getElementById("helpline-list"));
  for (const line of helplines) {
    list.append(
      el(
        "li",
        {},
        el(
          "a",
          { attrs: { href: `tel:${line.number}`, "aria-label": `${t("callNow")} ${line.number}, ${line.name}` } },
          el("strong", { text: line.number }),
          el("span", { text: line.name }),
        ),
      ),
    );
  }
}

async function load(question = "") {
  const form = document.getElementById("safety-form");
  const result = document.getElementById("safety-result");
  const conditions = [...form.querySelectorAll('input[name="conditions"]:checked')].map((box) => box.value);
  showLoading(result);
  try {
    const payload = { profile: getProfile(), hour: new Date().getHours(), conditions };
    if (question) payload.question = question;
    const data = await post("/api/safety", payload);
    renderHelplines(data.helplines);
    const tips = el("ol", { class: "tip-list" }, ...data.tips.map((tip) => el("li", { text: tip.text })));
    clear(result).append(
      data.answer ? answerBlock(data.answer) : null,
      el("div", { class: "panel" }, el("h2", { text: t("getTips") }), tips),
    );
  } catch (error) {
    showError(result, error);
  }
}

export const safetyView = {
  init() {
    const form = document.getElementById("safety-form");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      withBusy(form.querySelector('button[type="submit"]'), () => load(form.question.value.trim()));
    });
    form.querySelectorAll('input[name="conditions"]').forEach((box) => box.addEventListener("change", () => load()));
  },
  onShow() {
    load();
  },
};
