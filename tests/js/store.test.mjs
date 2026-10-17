import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { installBrowserStubs } from "./setup.mjs";

installBrowserStubs();
const store = await import("../../static/js/store.js");

beforeEach(() => {
  store.replaceEntries([]);
});

test("profile falls back to safe defaults and merges saved fields", () => {
  assert.equal(store.getProfile().language, "en");
  assert.equal(store.getProfile().weekly_goal, null);
  store.saveProfile({ work_type: "ride_driver", weekly_goal: 6000 });
  const profile = store.getProfile();
  assert.equal(profile.work_type, "ride_driver");
  assert.equal(profile.weekly_goal, 6000);
  assert.equal(profile.has_bank_account, true);
  assert.ok(store.hasProfile());
});

test("entries are kept sorted by day and local ids never reach the API", () => {
  store.addEntry({ day: "2026-10-15", platform: "Ola", gross: 900, hours: 8 });
  store.addEntry({ day: "2026-10-12", platform: "Uber", gross: 700, hours: 7 });
  assert.deepEqual(
    store.getEntries().map((e) => e.day),
    ["2026-10-12", "2026-10-15"],
  );
  for (const entry of store.entriesForApi()) assert.equal("id" in entry, false);
});

test("deleting an entry removes only that entry", () => {
  store.addEntry({ day: "2026-10-12", platform: "A", gross: 1, hours: 1 });
  store.addEntry({ day: "2026-10-13", platform: "B", gross: 1, hours: 1 });
  const [first] = store.getEntries();
  store.deleteEntry(first.id);
  assert.deepEqual(
    store.getEntries().map((e) => e.platform),
    ["B"],
  );
});

test("history is capped at 400 days to keep requests small", () => {
  const many = Array.from({ length: 450 }, (_, i) => ({ id: String(i), day: "2026-01-01", gross: 1, hours: 1 }));
  store.replaceEntries(many);
  assert.equal(store.getEntries().length, 400);
});
