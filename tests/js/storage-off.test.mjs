import assert from "node:assert/strict";
import { test } from "node:test";
import { installBrowserStubs } from "./setup.mjs";

// Private browsing can make localStorage throw: the app must keep working in memory.
installBrowserStubs({ storage: false });
const store = await import("../../static/js/store.js");

test("works in memory when storage is blocked", () => {
  store.saveProfile({ language: "hi" });
  assert.equal(store.getProfile().language, "hi");
  store.savePrefs({ largeText: true });
  assert.equal(store.getPrefs().largeText, true);
});
