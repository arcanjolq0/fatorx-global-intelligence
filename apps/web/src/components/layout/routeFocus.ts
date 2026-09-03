import { NavigationType } from "react-router";

export function shouldResetRouteScroll(navigationType: NavigationType, isInitialRoute: boolean) {
  return isInitialRoute || navigationType !== NavigationType.Pop;
}

export function focusRouteMainContent(main: HTMLElement | null, resetScroll: boolean) {
  if (resetScroll) {
    window.scrollTo({ behavior: "auto", left: 0, top: 0 });
  }

  main?.focus({ preventScroll: true });
}
