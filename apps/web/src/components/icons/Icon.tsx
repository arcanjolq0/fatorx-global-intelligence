import type { SVGProps } from "react";

export type IconName =
  | "add"
  | "audit"
  | "claims"
  | "entities"
  | "evidence"
  | "investigations"
  | "menu"
  | "overview"
  | "reports"
  | "reviews"
  | "search"
  | "settings"
  | "shield"
  | "sources"
  | "x";

export interface IconProps extends SVGProps<SVGSVGElement> {
  readonly name: IconName;
}

const paths: Readonly<Record<IconName, string>> = {
  add: "M12 5v14M5 12h14",
  audit: "M12 3 5 6v5c0 4.55 2.9 8.74 7 10 4.1-1.26 7-5.45 7-10V6l-7-3Zm-3 9 2 2 4-4",
  claims: "M7 3h10a2 2 0 0 1 2 2v14H5V5a2 2 0 0 1 2-2Zm2 5h6M9 12h6M9 16h4",
  entities: "M4 21V7l8-4 8 4v14M8 10h2m4 0h2m-8 4h2m4 0h2m-6 7v-3h4v3",
  evidence: "M6 3h8l4 4v14H6V3Zm8 0v5h5M9 12h6m-6 4h4",
  investigations: "M4 7h16v12H4V7Zm4 0V5h8v2M4 11h16",
  menu: "M4 6h16M4 12h16M4 18h16",
  overview: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  reports: "M6 3h8l4 4v14H6V3Zm8 0v5h5M9 17v-3m3 3v-6m3 6v-8",
  reviews: "M12 3 5 6v5c0 4.55 2.9 8.74 7 10 4.1-1.26 7-5.45 7-10V6l-7-3Zm-3 9 2 2 4-4",
  search: "m21 21-4.35-4.35M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm8 4 2-1-2-3-2 .5-1.5-1L16 5l-3-1-1 2h-2L9 4 6 5 5.5 7.5l-1.5 1L2 8l-2 3 2 1v2l-2 1 2 3 2-.5 1.5 1L6 21l3 1 1-2h2l1 2 3-1 .5-2.5 1.5-1 2 .5 2-3-2-1v-2Z",
  shield: "M12 3 5 6v5c0 4.55 2.9 8.74 7 10 4.1-1.26 7-5.45 7-10V6l-7-3Z",
  sources:
    "M4 6c0-1.1 3.58-2 8-2s8 .9 8 2-3.58 2-8 2-8-.9-8-2Zm0 0v6c0 1.1 3.58 2 8 2s8-.9 8-2V6m-16 6v6c0 1.1 3.58 2 8 2s8-.9 8-2v-6",
  x: "M6 6l12 12M18 6 6 18",
};

export function Icon({ name, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      stroke="currentColor"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      {...props}
    >
      <path d={paths[name]} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
