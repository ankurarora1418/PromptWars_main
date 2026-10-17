// Safe DOM helpers. All dynamic text goes through textContent — never innerHTML —
// so AI output or user input can never inject markup or script.
import { t } from "./i18n.js";
import { speechSupported, toggleSpeak } from "./speech.js";

/** Create an element. props: {class, text, attrs, on}; children: nodes or strings. */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  if (props.class) node.className = props.class;
  if (props.text !== undefined && props.text !== null) node.textContent = String(props.text);
  for (const [name, value] of Object.entries(props.attrs || {})) {
    if (value !== undefined && value !== null && value !== false) node.setAttribute(name, value === true ? "" : String(value));
  }
  for (const [event, handler] of Object.entries(props.on || {})) node.addEventListener(event, handler);
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

const LIST_ITEM = /^\s*(?:[-•*]|\d+[.)])\s+/;

/** Render plain model text as paragraphs and bullet lists. */
export function renderText(text) {
  const fragment = document.createDocumentFragment();
  let list = null;
  for (const raw of text.replace(/\*\*/g, "").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      list = null;
      continue;
    }
    if (LIST_ITEM.test(line)) {
      if (!list) {
        list = el("ul");
        fragment.append(list);
      }
      list.append(el("li", { text: line.replace(LIST_ITEM, "") }));
    } else {
      list = null;
      fragment.append(el("p", { text: line.replace(/^#+\s*/, "") }));
    }
  }
  return fragment;
}

export function copyButton(getText) {
  return el("button", {
    class: "btn btn-quiet",
    attrs: { type: "button" },
    text: t("copy"),
    on: {
      click: async () => {
        try {
          await navigator.clipboard.writeText(getText());
          toast(t("copied"));
        } catch {
          toast(t("errorGeneric"));
        }
      },
    },
  });
}

export function speakButton(getText, lang) {
  if (!speechSupported()) return null;
  const button = el("button", { class: "btn btn-quiet", attrs: { type: "button", "aria-pressed": "false" }, text: t("readAloud") });
  button.addEventListener("click", () => toggleSpeak(getText(), lang, button, { play: t("readAloud"), stop: t("stopReading") }));
  return button;
}

/** A rendered AI answer with source label, privacy note, read-aloud and copy. */
export function answerBlock(answer, extraActions = []) {
  const body = el("div", { attrs: { lang: answer.language } }, renderText(answer.text));
  const sourceLabel = answer.source === "gemini" ? t("sourceGemini") : t("sourceOffline");
  return el(
    "div",
    { class: "answer" },
    answer.privacy_note ? el("p", { class: "privacy-note", text: answer.privacy_note }) : null,
    body,
    el(
      "div",
      { class: "answer-meta" },
      el("span", { class: "source-tag", text: sourceLabel }),
      speakButton(() => answer.text, answer.language),
      copyButton(() => answer.text),
      ...extraActions,
    ),
  );
}

export function showLoading(container) {
  clear(container).append(el("p", { class: "loading", attrs: { role: "status" }, text: t("thinking") }));
}

export function showError(container, error) {
  clear(container).append(el("p", { class: "error-box", attrs: { role: "alert" }, text: error?.message || t("errorGeneric") }));
}

let toastTimer = null;
export function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 2600);
}

/** Disable a button while an async action runs. */
export async function withBusy(button, action) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

/** Validate a form natively; mark invalid fields and focus the first one. */
export function validateForm(form, errorNode) {
  let first = null;
  for (const field of form.querySelectorAll("input, select, textarea")) {
    const valid = field.checkValidity();
    field.setAttribute("aria-invalid", valid ? "false" : "true");
    if (!valid && !first) first = field;
  }
  if (errorNode) errorNode.textContent = first ? t("fixErrors") : "";
  if (first) first.focus();
  return !first;
}

export function formatMoney(value) {
  if (value === null || value === undefined) return "—";
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

export function todayISO() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now - offset).toISOString().slice(0, 10);
}
