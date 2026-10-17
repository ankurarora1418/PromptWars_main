import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { installBrowserStubs } from "./setup.mjs";

installBrowserStubs();
globalThis.fetch = async (url) => {
  const code = url.match(/i18n\/(\w+)\.json$/)[1];
  const body = await readFile(new URL(`../../static/i18n/${code}.json`, import.meta.url), "utf8");
  return { ok: true, json: async () => JSON.parse(body) };
};
const i18n = await import("../../static/js/i18n.js");

test("unsupported UI languages fall back to English menus", async () => {
  assert.equal(await i18n.loadLanguage("ta"), "en");
  assert.equal(document.documentElement.lang, "en");
  assert.equal(i18n.hasUiTranslation("ta"), false);
});

test("Hindi menus load and placeholders are filled", async () => {
  assert.equal(await i18n.loadLanguage("hi"), "hi");
  assert.equal(document.documentElement.lang, "hi");
  const text = i18n.t("goalProgress", { percent: 40 });
  assert.match(text, /40%/);
  assert.doesNotMatch(text, /\{percent\}/);
});

test("missing variables stay visible instead of printing 'undefined'", async () => {
  await i18n.loadLanguage("en");
  assert.equal(i18n.t("weeklyGoalTitle"), "This week's goal: {goal}");
  assert.equal(i18n.t("no-such-key"), "no-such-key");
});
