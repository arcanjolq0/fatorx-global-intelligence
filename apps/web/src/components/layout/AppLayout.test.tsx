import { NavigationType } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { focusRouteMainContent, shouldResetRouteScroll } from "./routeFocus";

describe("AppLayout route focus policy", () => {
  it("resets initial and forward navigations, while preserving browser history scroll", () => {
    expect(shouldResetRouteScroll(NavigationType.Pop, true)).toBe(true);
    expect(shouldResetRouteScroll(NavigationType.Push, false)).toBe(true);
    expect(shouldResetRouteScroll(NavigationType.Replace, false)).toBe(true);
    expect(shouldResetRouteScroll(NavigationType.Pop, false)).toBe(false);
  });

  it("focuses main without scrolling it and resets only when the policy requires", () => {
    const main = document.createElement("main");
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    const focus = vi.spyOn(main, "focus");

    focusRouteMainContent(main, true);
    expect(scrollTo).toHaveBeenCalledWith({ behavior: "auto", left: 0, top: 0 });
    expect(focus).toHaveBeenCalledWith({ preventScroll: true });

    scrollTo.mockClear();
    focusRouteMainContent(main, false);
    expect(scrollTo).not.toHaveBeenCalled();
    expect(focus).toHaveBeenLastCalledWith({ preventScroll: true });
  });
});
