// Documents: explain pasted text or a photo; show the checklist for a chosen scheme.
import { post } from "../api.js";
import { answerBlock, clear, el, showError, showLoading, withBusy } from "../dom.js";
import { t } from "../i18n.js";
import { getProfile } from "../store.js";

const MAX_SIDE = 1600; // shrink photos on the phone: faster upload, less data, enough for reading
const MAX_SOURCE_BYTES = 15_000_000;

/** Resize and re-encode a photo as JPEG. Re-encoding also drops EXIF (e.g. GPS location). */
async function prepareImage(file) {
  if (file.size > MAX_SOURCE_BYTES) throw new Error(t("photoTooBig"));
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  const dataUrl = canvas.toDataURL("image/jpeg", 0.82);
  return { image_base64: dataUrl.split(",")[1], image_mime: "image/jpeg" };
}

async function showChecklist(schemeId) {
  const slot = document.getElementById("checklist-result");
  if (!schemeId) {
    clear(slot);
    return;
  }
  showLoading(slot);
  try {
    const data = await post("/api/documents/checklist", { profile: getProfile(), scheme_id: schemeId });
    const items = data.documents.map((doc) =>
      el("li", {}, el("label", { class: "check-item" }, el("input", { attrs: { type: "checkbox" } }), ` ${doc.name}`)),
    );
    clear(slot).append(
      el(
        "div",
        { class: "panel" },
        el("h2", { text: t("checklistTitle", { scheme: data.scheme_name }) }),
        el("ul", { class: "checks" }, ...items),
        el("p", {}, el("strong", { text: `${t("howToApply")}: ` }), data.how_to_apply),
        el("p", {}, el("a", { attrs: { href: data.official_url, target: "_blank", rel: "noopener noreferrer" }, text: t("officialSite") })),
      ),
    );
  } catch (error) {
    showError(slot, error);
  }
}

async function submit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.getElementById("document-error");
  const result = document.getElementById("document-result");
  const text = form.text.value.trim();
  const file = form.photo.files[0];
  if (!text && !file) {
    error.textContent = t("needDocument");
    form.text.focus();
    return;
  }
  error.textContent = "";
  showLoading(result);
  await withBusy(form.querySelector('button[type="submit"]'), async () => {
    try {
      const payload = { profile: getProfile() };
      if (text) payload.text = text;
      if (form.question.value.trim()) payload.question = form.question.value.trim();
      if (file) Object.assign(payload, await prepareImage(file));
      const data = await post("/api/documents/explain", payload);
      clear(result).append(answerBlock(data.answer));
    } catch (err) {
      showError(result, err);
    }
  });
}

export const documentsView = {
  init() {
    document.getElementById("document-form").addEventListener("submit", submit);
  },
  onShow(params) {
    showChecklist(params.scheme_id);
  },
};
