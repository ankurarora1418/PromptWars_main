// Profile dialog: work type, state, age, income and a few yes/no facts.
import { getProfile, saveProfile } from "../store.js";
import { t } from "../i18n.js";
import { toast } from "../dom.js";

const dialog = () => document.getElementById("profile-dialog");
const form = () => document.getElementById("profile-form");
const CHECKBOXES = ["eshram_registered", "has_bank_account", "has_epfo_or_esic", "pays_income_tax"];
let onSaved = () => {};

export function initProfile({ languages, states, onSave }) {
  onSaved = onSave;
  const langSelect = document.getElementById("p-language");
  langSelect.replaceChildren(...languages.map((l) => new Option(l.name, l.code)));
  const stateSelect = document.getElementById("p-state");
  stateSelect.replaceChildren(...states.map((s) => new Option(s, s)));

  form().addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form().reportValidity()) return;
    const data = new FormData(form());
    const numberOrNull = (name) => (data.get(name) === "" ? null : Number(data.get(name)));
    const profile = {
      language: data.get("language"),
      work_type: data.get("work_type"),
      state: data.get("state"),
      shift: data.get("shift"),
      age: numberOrNull("age"),
      monthly_income: numberOrNull("monthly_income"),
      weekly_goal: numberOrNull("weekly_goal"),
    };
    CHECKBOXES.forEach((name) => {
      profile[name] = data.get(name) === "on";
    });
    saveProfile(profile);
    dialog().close();
    toast(t("profileSaved"));
    onSaved(profile);
  });
}

export function openProfile() {
  const profile = getProfile();
  const f = form();
  f.language.value = profile.language;
  f.work_type.value = profile.work_type;
  f.state.value = profile.state;
  f.shift.value = profile.shift;
  f.age.value = profile.age ?? "";
  f.monthly_income.value = profile.monthly_income ?? "";
  f.weekly_goal.value = profile.weekly_goal ?? "";
  CHECKBOXES.forEach((name) => {
    f[name].checked = Boolean(profile[name]);
  });
  dialog().showModal();
  f.work_type.focus();
}
