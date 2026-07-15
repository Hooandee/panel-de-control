import { theme } from "./theme";
import { FALLBACK_ACCENT_RGB } from "./system/accentColor";

// Steam stamps `gpfocus` on the element holding gamepad focus; scoping the ring to
// our root covers every control. Colour comes from the --pdc-accent-rgb variable.
export const PDC_ROOT = "pdc-root";
export const FOCUS_STYLE_ID = "pdc-focus-styles";

// box-shadow (not outline: this CEF draws outline square) + a forced radius so square
// controls round too; a dark gap ring, the accent ring, then a soft halo.
export function buildFocusCss(): string {
  const ring = `rgb(var(--pdc-accent-rgb, ${FALLBACK_ACCENT_RGB}))`;
  const halo = `rgba(var(--pdc-accent-rgb, ${FALLBACK_ACCENT_RGB}), 0.55)`;
  return `
.${PDC_ROOT} .gpfocus {
  border-radius: 10px !important;
  box-shadow: 0 0 0 3px ${theme.color.surface},
              0 0 0 5px ${ring},
              0 0 11px 4px ${halo} !important;
  filter: brightness(1.05);
  transition: box-shadow 120ms ease, filter 120ms ease;
  position: relative;
  z-index: 1;
}`.trim();
}

export function ensureFocusStyles(doc: Document = document): void {
  try {
    if (doc.getElementById(FOCUS_STYLE_ID)) return;
    const el = doc.createElement("style");
    el.id = FOCUS_STYLE_ID;
    el.textContent = buildFocusCss();
    doc.head.appendChild(el);
  } catch {
    /* best-effort */
  }
}
