import type { ThemeClaim, ThirdPartySignal } from "../core/arbiter";
import { steamClass } from "./steamClasses";

export const CLAIM_PROPERTY = "--pdc-ambient-claim";
export const CLAIM_NAME_PROPERTY = "--pdc-ambient-claim-name";
const CLAIM_ID = /^[A-Za-z0-9._-]{1,64}$/;

/** Surfaces that sit above our layer inside BasicHome and would hide it if a theme paints them. */
export const PAINTABLE_KEYS = ["ScrollArea", "TabContentsScroll", "RecentGamesContainer", "RecentGamesInnerContainer", "RecentSection", "GamepadLibrary", "BackgroundGlass"] as const;

function unquote(value: string): string {
  return value.trim().replace(/^["']|["']$/g, "").trim();
}

/** Cooperative themes declare `--pdc-ambient-claim` on :root; old Panels simply ignore it. */
export function readThemeClaim(doc: Document): ThemeClaim | null {
  const style = doc.defaultView?.getComputedStyle(doc.documentElement);
  if (!style) return null;
  const id = unquote(style.getPropertyValue(CLAIM_PROPERTY));
  if (!CLAIM_ID.test(id)) return null;
  const name = unquote(style.getPropertyValue(CLAIM_NAME_PROPERTY)).slice(0, 60);
  return { id, name: name || id };
}

function paints(style: CSSStyleDeclaration): boolean {
  if (style.backgroundImage && style.backgroundImage !== "none") return true;
  const match = /rgba?\(([^)]+)\)/.exec(style.backgroundColor || "");
  if (!match) return false;
  const parts = match[1].split(",").map((p) => Number.parseFloat(p));
  return (parts.length < 4 ? 1 : parts[3]) >= 0.6;
}

function coversViewport(style: CSSStyleDeclaration, host: DOMRect, minArea: number): boolean {
  if (style.position === "fixed") return true;
  return style.position === "absolute" && host.width * host.height >= minArea && style.inset.split(" ").every((v) => Number.parseFloat(v) === 0);
}

/**
 * A non-cooperative painter is only reported with high confidence when a large surface above our
 * layer paints over it while CSS Loader styles are present. Anything less stays silent.
 */
export interface Painter {
  id: string;
  key: string;
  part: "" | "::before" | "::after";
}

/** Large surfaces above our layer that paint over it, as element or pseudo-element. */
export function detectPainters(doc: Document): Painter[] {
  const view = doc.defaultView;
  if (!view) return [];
  const minArea = view.innerWidth * view.innerHeight * 0.6;
  const painters: Painter[] = [];
  for (const key of PAINTABLE_KEYS) {
    const cls = steamClass(key);
    if (!cls) continue;
    const element = doc.querySelector<HTMLElement>(`.${cls}`);
    if (!element) continue;
    const rect = element.getBoundingClientRect();
    if (rect.width * rect.height >= minArea && paints(view.getComputedStyle(element))) painters.push({ id: `css:${key}`, key, part: "" });
    for (const part of ["::before", "::after"] as const) {
      const style = view.getComputedStyle(element, part);
      if (style.content !== "none" && style.content !== "normal" && coversViewport(style, rect, minArea) && paints(style)) {
        painters.push({ id: `css:${key}${part}`, key, part });
      }
    }
  }
  return painters;
}

export function detectThirdParty(doc: Document, hasCssLoaderStyles: boolean = !!doc.querySelector("style.css-loader-style")): ThirdPartySignal {
  if (!hasCssLoaderStyles) return { confidence: "none" };
  const painters = detectPainters(doc);
  if (painters.length === 0) return { confidence: "none" };
  const candidates = painters.map((p) => p.id);
  return { confidence: painters.length === 1 ? "high" : "low", id: candidates[0], candidates };
}

const NEUTRALIZE_ID = "pdc-ambient-neutralize";
const PAINTER_ID = /^css:([A-Za-z]+)(::before|::after)?$/;

/** Clears only the background of painters the user chose to see through; scoped to Panel owning it. */
export function applyNeutralizer(doc: Document, ids: readonly string[]): void {
  const rules = ids.flatMap((id) => {
    const match = PAINTER_ID.exec(id);
    const cls = match ? steamClass(match[1]) : null;
    return cls ? [`:root[data-pdc-ambient-background="panel"] .${cls}${match![2] ?? ""}{background:none!important;background-color:transparent!important}`] : [];
  });
  const existing = doc.getElementById(NEUTRALIZE_ID);
  if (rules.length === 0) {
    existing?.remove();
    return;
  }
  const style = existing ?? doc.head.appendChild(Object.assign(doc.createElement("style"), { id: NEUTRALIZE_ID }));
  const text = rules.join("\n");
  if (style.textContent !== text) style.textContent = text;
}
