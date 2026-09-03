import "@testing-library/jest-dom/vitest";

Object.defineProperty(window, "scrollTo", {
  configurable: true,
  value: () => undefined,
  writable: true,
});

const blockedFetch: typeof fetch = () => {
  throw new Error("Network access is disabled in frontend tests.");
};

Object.defineProperty(globalThis, "fetch", {
  configurable: false,
  value: blockedFetch,
  writable: false,
});
