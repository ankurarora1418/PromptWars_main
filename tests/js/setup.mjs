// Minimal browser stand-ins so the app's ES modules can be unit-tested in Node (no bundler).
export function installBrowserStubs({ storage = true } = {}) {
  const items = new Map();
  globalThis.window = {
    localStorage: storage
      ? {
          getItem: (k) => (items.has(k) ? items.get(k) : null),
          setItem: (k, v) => items.set(k, String(v)),
        }
      : {
          getItem: () => {
            throw new Error("storage disabled");
          },
          setItem: () => {
            throw new Error("storage disabled");
          },
        },
  };
  globalThis.document = { documentElement: { lang: "en" } };
  return items;
}
