import "@testing-library/jest-dom/vitest";

const blockedFetch: typeof fetch = () => {
  throw new Error("Network access is disabled in frontend tests.");
};

Object.defineProperty(globalThis, "fetch", {
  configurable: false,
  value: blockedFetch,
  writable: false,
});
