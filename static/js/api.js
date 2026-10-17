// Thin fetch wrapper: JSON in/out, timeout, and friendly, translated error messages.
import { t } from "./i18n.js";

const TIMEOUT_MS = 45000;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(path, { ...options, signal: controller.signal, credentials: "same-origin" });
  } catch {
    throw new ApiError(t("errorNetwork"), 0);
  } finally {
    clearTimeout(timer);
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    if (response.status === 429) throw new ApiError(t("errorRateLimit"), 429);
    if (response.status === 422) {
      const detail = typeof body?.detail === "string" && body.detail !== "Please check the form." ? body.detail : t("errorForm");
      throw new ApiError(detail, 422);
    }
    throw new ApiError(t("errorGeneric"), response.status);
  }
  return body;
}

export function get(path) {
  return request(path);
}

export function post(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
