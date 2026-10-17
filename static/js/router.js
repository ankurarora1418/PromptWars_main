// Hash router. Views can be opened with parameters, which is how modules hand work to each
// other (e.g. an earnings alert opens the complaint form pre-filled).

const views = new Map();
let pendingParams = {};
let currentView = null;

export function registerView(name, view) {
  views.set(name, view);
}

export function currentViewName() {
  return currentView;
}

export function navigate(name, params = {}) {
  pendingParams = params;
  if (location.hash === `#${name}`) show(name);
  else location.hash = name;
}

export function show(name, { focus = true } = {}) {
  const target = views.has(name) ? name : "home";
  const params = pendingParams;
  pendingParams = {};
  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.id !== `view-${target}`;
  });
  document.querySelectorAll(".tabs a").forEach((link) => {
    if (link.dataset.view === target) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const heading = document.querySelector(`#view-${target} h1`);
  document.title = `${heading ? heading.textContent : "Saathi"} — Saathi`;
  if (focus && heading && currentView !== null) heading.focus();
  currentView = target;
  window.scrollTo(0, 0);
  views.get(target).onShow?.(params);
}

export function startRouter() {
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1) || "home", { focus: false });
}
