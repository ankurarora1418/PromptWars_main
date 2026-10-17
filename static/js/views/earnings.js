// Earnings: log days, see exact take-home maths, alerts that link to other modules.
import { post } from "../api.js";
import { answerBlock, clear, el, formatMoney, showError, showLoading, toast, todayISO, validateForm, withBusy } from "../dom.js";
import { t } from "../i18n.js";
import { navigate } from "../router.js";
import { addEntry, deleteEntry, entriesForApi, getEntries, getProfile, replaceEntries } from "../store.js";

const NUMBER_FIELDS = ["gross", "tips", "hours", "km", "fuel_cost", "other_expenses", "platform_deductions"];

function stat(label, value, main = false) {
  return el("div", { class: main ? "stat stat-main" : "stat" }, el("dt", { text: label }), el("dd", { text: value }));
}

function chart(daily) {
  const values = daily.map((d) => d.net);
  const max = Math.max(...values.map(Math.abs), 1);
  const bars = el("div", { class: "chart", attrs: { "aria-hidden": "true" } });
  for (const day of daily.slice(-14)) {
    const bar = el("div", { class: day.net < 0 ? "bar negative" : "bar", attrs: { title: `${day.day}: ${formatMoney(day.net)}` } });
    bar.style.height = `${Math.max(4, (Math.abs(day.net) / max) * 100)}%`;
    bars.append(bar);
  }
  const summary = t("chartSummary", {
    days: daily.length,
    max: Math.round(Math.max(...values)).toLocaleString("en-IN"),
    min: Math.round(Math.min(...values)).toLocaleString("en-IN"),
  });
  return el(
    "figure",
    { class: "panel", attrs: { "aria-label": t("dailyChart") } },
    el("h2", { text: t("dailyChart") }),
    bars,
    el("figcaption", { class: "chart-caption", text: summary }),
  );
}

function alertBox(alert) {
  const actions = [];
  if (alert.action?.startsWith("grievance:")) {
    const params = { issue_type: alert.action.split(":")[1] };
    if (alert.code === "high_deductions") params.amount = alert.data.amount;
    actions.push(
      el("button", { class: "btn btn-secondary", attrs: { type: "button" }, text: t("draftComplaint"), on: { click: () => navigate("grievance", params) } }),
    );
  } else if (alert.action === "safety") {
    actions.push(el("button", { class: "btn btn-quiet", attrs: { type: "button" }, text: t("seeSafety"), on: { click: () => navigate("safety") } }));
  }
  return el("div", { class: `alert ${alert.severity}` }, el("p", { text: alert.message }), actions.length ? el("p", {}, ...actions) : null);
}

function renderEntries() {
  const list = clear(document.getElementById("entry-list"));
  const entries = getEntries();
  if (!entries.length) {
    list.append(el("li", { text: t("noEntries") }));
    return;
  }
  for (const entry of [...entries].reverse()) {
    list.append(
      el(
        "li",
        {},
        el("span", { text: `${entry.day} · ${entry.platform} · ${formatMoney(entry.gross)} · ${entry.hours}h` }),
        el("button", {
          class: "btn btn-quiet btn-danger",
          attrs: { type: "button", "aria-label": t("deleteEntryLabel", { day: entry.day, platform: entry.platform }) },
          text: t("deleteEntry"),
          on: {
            click: () => {
              deleteEntry(entry.id);
              toast(t("dayDeleted"));
              refresh();
            },
          },
        }),
      ),
    );
  }
}

async function refresh() {
  renderEntries();
  const result = document.getElementById("earnings-result");
  const entries = entriesForApi();
  if (!entries.length) {
    clear(result);
    return;
  }
  showLoading(result);
  try {
    const data = await post("/api/earnings/summary", { profile: getProfile(), entries });
    const s = data.summary;
    clear(result).append(
      el(
        "dl",
        { class: "stats" },
        stat(t("netTakeHome"), formatMoney(s.net_earnings), true),
        stat(t("perHour"), formatMoney(s.net_per_hour)),
        stat(t("perKm"), s.net_per_km === null ? "—" : `₹${s.net_per_km}`),
        stat(t("daysWorked"), String(s.days_worked)),
      ),
      ...s.alerts.filter((a) => a.code !== "best_platform").map(alertBox),
      data.explanation ? answerBlock(data.explanation) : null,
      s.daily.length > 1 ? chart(s.daily) : null,
    );
  } catch (error) {
    showError(result, error);
  }
}

function sampleFortnight() {
  const entries = [];
  const today = new Date();
  for (let offset = 13; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - offset);
    const day = new Date(date - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const thisWeek = offset <= 6;
    const platform = offset % 3 === 0 ? "Zomato" : "Swiggy";
    entries.push({
      id: `sample-${offset}`,
      day,
      platform,
      gross: thisWeek ? 780 + (offset % 3) * 40 : 1150 + (offset % 3) * 50,
      tips: offset % 2 ? 30 : 0,
      hours: offset === 2 ? 12.5 : 9,
      km: 70,
      fuel_cost: 180,
      other_expenses: 20,
      platform_deductions: thisWeek && offset % 2 === 0 ? 150 : 40,
    });
  }
  return entries;
}

export const earningsView = {
  init() {
    const form = document.getElementById("earning-form");
    form.day.value = todayISO();
    form.day.max = todayISO();
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!validateForm(form, document.getElementById("earning-error"))) return;
      const data = new FormData(form);
      const entry = { day: data.get("day"), platform: data.get("platform").trim() || "Other" };
      NUMBER_FIELDS.forEach((name) => {
        entry[name] = Number(data.get(name) || 0);
      });
      addEntry(entry);
      toast(t("daySaved"));
      form.reset();
      form.day.value = todayISO();
      await withBusy(form.querySelector('button[type="submit"]'), refresh);
    });
    document.getElementById("sample-week").addEventListener("click", () => {
      replaceEntries(sampleFortnight());
      toast(t("sampleLoaded"));
      refresh();
    });
    document.getElementById("clear-entries").addEventListener("click", () => {
      if (window.confirm(t("confirmClear"))) {
        replaceEntries([]);
        toast(t("allDeleted"));
        refresh();
      }
    });
  },
  onShow() {
    refresh();
  },
};
