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

/** Literal colors only. Unsupported syntax stays ambiguous, never evidence of ownership. */
function literalColor(value: string): string | null {
  value = value.trim().toLowerCase();
  if (value === "transparent") return "0,0,0,0";
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(value);
  if (hex) {
    const digits = hex[1].length === 3 ? [...hex[1]].map(c => c + c).join("") : hex[1];
    return `${parseInt(digits.slice(0, 2), 16)},${parseInt(digits.slice(2, 4), 16)},${parseInt(digits.slice(4, 6), 16)},1`;
  }
  const rgb = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$/.exec(value);
  return rgb ? `${+rgb[1]},${+rgb[2]},${+rgb[3]},${rgb[4] === undefined ? 1 : +rgb[4]}` : null;
}

interface BackgroundRule { selectors: string[]; style: CSSStyleDeclaration; loader: boolean; uncertain: boolean }

/** One CSSOM walk per check; no CSSOM writes, DOM clones, resources or extra layout reads. */
function backgroundRules(doc: Document): { rules: BackgroundRule[]; unreadable: boolean } {
  const rules: BackgroundRule[] = [];
  let unreadable = false;
  const loaderSheets = new Set(Array.from(doc.querySelectorAll<HTMLStyleElement>("style.css-loader-style"), el => el.sheet));
  const walk = (list: CSSRuleList, loader: boolean, uncertain: boolean) => {
    for (const rule of Array.from(list)) {
      if (rule.type === 1) {
        const styleRule = rule as CSSStyleRule;
        if (styleRule.cssRules?.length) unreadable = true; // nesting needs its ancestor selector/cascade
        if (["background", "background-image", "background-color", "all"].some(key => styleRule.style.getPropertyValue(key)))
          rules.push({ selectors: splitSelectors(styleRule.selectorText), style: styleRule.style, loader, uncertain: uncertain || !!styleRule.style.getPropertyValue("all") });
      } else if (rule.type === 4) {
        const media = rule as CSSMediaRule;
        if (doc.defaultView?.matchMedia(media.conditionText).matches) walk(media.cssRules, loader, uncertain);
      } else if ("cssRules" in rule) {
        // Container/supports/layer/nesting conditions are not reconstructed by this detector.
        walk((rule as CSSGroupingRule).cssRules, loader, true);
      } else if (rule.type === 3) unreadable = true; // imported rules may contribute a native value
    }
  };
  const sheets = new Set(Array.from(doc.styleSheets));
  try { for (const sheet of doc.adoptedStyleSheets ?? []) sheets.add(sheet); } catch { unreadable = true; }
  for (const sheet of sheets) {
    if (sheet.disabled) continue;
    if (sheet.media?.mediaText && !doc.defaultView?.matchMedia(sheet.media.mediaText).matches) continue;
    try { walk(sheet.cssRules, loaderSheets.has(sheet), false); } catch { unreadable = true; }
  }
  return { rules, unreadable };
}

function splitSelectors(selector: string): string[] {
  // Split only top-level commas; :is/:not/:has and quoted attribute values remain intact.
  const branches: string[] = [];
  let start = 0, depth = 0, quote = "", escaped = false;
  for (let i = 0; i < selector.length; i++) {
    const c = selector[i];
    if (escaped) { escaped = false; continue; }
    if (c === "\\") { escaped = true; continue; }
    if (quote) { if (c === quote) quote = ""; continue; }
    if (c === "'" || c === '\"') { quote = c; continue; }
    if (c === "(" || c === "[") depth++;
    if (c === ")" || c === "]") depth--;
    if (c === "," && depth === 0) { branches.push(selector.slice(start, i)); start = i + 1; }
  }
  branches.push(selector.slice(start));
  return branches;
}

function matchesPainter(element: Element, branches: string[], part: Painter["part"]): boolean | null {
  let unknown = false;
  for (const branch of branches) {
    const pseudo = /::?(before|after)\s*$/.exec(branch);
    if ((pseudo ? `::${pseudo[1]}` : "") !== part) continue;
    try { if (element.matches(pseudo ? branch.slice(0, pseudo.index).trim() || "*" : branch.trim())) return true; }
    catch { unknown = true; }
  }
  return unknown ? null : false;
}

function literalBackground(style: CSSStyleDeclaration, property: string): string | null {
  const value = style.getPropertyValue(property).trim();
  if (!value || /var\(|currentcolor|inherit|initial|unset|revert/i.test(value)) return null;
  return property === "background-color" ? literalColor(value) : value;
}

/** Attribute only literal, matching backgrounds. Unknown matching Loader backgrounds remain low
 * confidence for manual selection; a cosmetic Loader never inherits ownership of native paint. */
export function detectThirdParty(doc: Document, hasCssLoaderStyles: boolean = !!doc.querySelector("style.css-loader-style")): ThirdPartySignal {
  if (!hasCssLoaderStyles) return { confidence: "none" };
  const painters = detectPainters(doc);
  if (!painters.length) return { confidence: "none" };
  const { rules, unreadable } = backgroundRules(doc);
  const candidates: string[] = [];
  let uncertainCandidate = false;
  for (const painter of painters) {
    const cls = steamClass(painter.key);
    const element = cls ? doc.querySelector<HTMLElement>(`.${cls}`) : null;
    const actual = element && doc.defaultView?.getComputedStyle(element, painter.part || null);
    if (!element || !actual) continue;
    const evaluated = rules.map(rule => ({rule, matches: matchesPainter(element, rule.selectors, painter.part)}));
    const matched = evaluated.filter(item => item.matches === true).map(item => item.rule);
    const hasBackground = (style: CSSStyleDeclaration) => ["background", "background-image", "background-color"].some(key => style.getPropertyValue(key));
    if (!matched.some(rule => rule.loader && hasBackground(rule.style))) continue;
    // Inline native declarations and rules that cannot be safely parsed may explain the live value.
    if (!painter.part) matched.push({selectors:[],style:element.style,loader:false,uncertain:!!element.style.getPropertyValue("all")});
    const hasReset = matched.some(rule => !!rule.style.getPropertyValue("all"));
    const unknownNativeSelector = evaluated.some(item => !item.rule.loader && item.matches === null);
    let proven = false, unknown = false;
    for (const property of ["background-image", "background-color"]) {
      const live = literalBackground(actual, property);
      if (property === "background-image" && live === "none") continue;
      if (property === "background-color" && !paints({backgroundImage:"none",backgroundColor:actual.backgroundColor} as CSSStyleDeclaration)) continue;
      const declaring = matched.filter(rule => rule.style.getPropertyValue(property) || rule.style.getPropertyValue("background") || rule.style.getPropertyValue("all"));
      const loader = declaring.filter(rule => rule.loader && hasBackground(rule.style));
      if (!loader.length) continue;
      const exactLoader = loader.some(rule => !rule.uncertain && live !== null && literalBackground(rule.style, property) === live);
      const unknownLoader = loader.some(rule => rule.uncertain || literalBackground(rule.style, property) === null);
      const nativeCanExplain = declaring.some(rule => !rule.loader && (rule.uncertain || literalBackground(rule.style, property) === null || literalBackground(rule.style, property) === live));
      if (exactLoader && !hasReset && !nativeCanExplain && !unreadable && !unknownNativeSelector && (!actual.animationName || actual.animationName === "none")) proven = true;
      else if (exactLoader || unknownLoader) unknown = true;
    }
    if (proven || unknown) { candidates.push(painter.id); if (!proven || unknown) uncertainCandidate = true; }
  }
  if (!candidates.length) return { confidence: "none" };
  return { confidence: candidates.length === 1 && !uncertainCandidate ? "high" : "low", id: candidates[0], candidates };
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
