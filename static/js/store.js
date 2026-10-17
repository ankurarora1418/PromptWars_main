// Everything personal stays in this browser. Storage can be unavailable (private mode),
// so every read and write is guarded and the app still works for the session.

const KEYS = { profile: "saathi.profile", entries: "saathi.entries", personal: "saathi.personal", prefs: "saathi.prefs" };
const memory = {};

function read(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return key in memory ? memory[key] : fallback;
  }
}

function write(key, value) {
  memory[key] = value;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: keep in memory only */
  }
}

export const DEFAULT_PROFILE = {
  language: "en",
  work_type: "delivery",
  state: "Delhi",
  age: null,
  monthly_income: null,
  shift: "day",
  has_epfo_or_esic: false,
  pays_income_tax: false,
  eshram_registered: false,
  has_bank_account: true,
};

export function hasProfile() {
  return read(KEYS.profile, null) !== null;
}

export function getProfile() {
  return { ...DEFAULT_PROFILE, ...read(KEYS.profile, {}) };
}

export function saveProfile(profile) {
  write(KEYS.profile, { ...getProfile(), ...profile });
}

/** Entries as stored (with local ids). */
export function getEntries() {
  return read(KEYS.entries, []);
}

/** Entries without local-only fields, ready for the API. */
export function entriesForApi() {
  return getEntries().map(({ id, ...entry }) => entry);
}

export function addEntry(entry) {
  const entries = getEntries();
  entries.push({ ...entry, id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}` });
  entries.sort((a, b) => a.day.localeCompare(b.day));
  write(KEYS.entries, entries.slice(-400));
}

export function replaceEntries(entries) {
  write(KEYS.entries, entries.slice(-400));
}

export function deleteEntry(id) {
  write(KEYS.entries, getEntries().filter((entry) => entry.id !== id));
}

export function getPersonal() {
  return read(KEYS.personal, { name: "", phone: "", worker_id: "" });
}

export function savePersonal(details) {
  write(KEYS.personal, details);
}

export function getPrefs() {
  return read(KEYS.prefs, { largeText: false });
}

export function savePrefs(prefs) {
  write(KEYS.prefs, { ...getPrefs(), ...prefs });
}
