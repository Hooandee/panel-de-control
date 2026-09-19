import { theme } from "./theme";
import { FALLBACK_ACCENT_RGB } from "./system/accentColor";

// Steam stamps `gpfocus` on the element holding gamepad focus; scoping the ring to
// our root covers every control. Colour comes from the --pdc-accent-rgb variable.
export const PDC_ROOT = "pdc-root";
export const FOCUS_STYLE_ID = "pdc-focus-styles";
export const PDC_TABSTRIP = "pdc-tabstrip";

// box-shadow (not outline: this CEF draws outline square) + a forced radius so square
// controls round too; a dark gap ring, the accent ring, then a soft halo.
export function buildFocusCss(): string {
  const ring = `rgb(var(--pdc-accent-rgb, ${FALLBACK_ACCENT_RGB}))`;
  const halo = `rgba(var(--pdc-accent-rgb, ${FALLBACK_ACCENT_RGB}), 0.55)`;
  return `
.${PDC_ROOT} .gpfocus {
  border-radius: var(--pdc-focus-radius, 10px) !important;
  box-shadow: 0 0 0 3px ${theme.color.surface},
              0 0 0 5px ${ring},
              0 0 11px 4px ${halo} !important;
  filter: brightness(1.05);
  transition: box-shadow 120ms ease, filter 120ms ease;
  position: relative;
  z-index: 1;
}
.${PDC_ROOT} .pdc-hud-slider {
  margin-inline: 0 !important;
  padding-block: 6px !important;
}
/* Steam fixes this inner slider row at 270px, wider than nested QAM cards. */
.${PDC_ROOT} .pdc-hud-slider > div > div {
  min-width: 0 !important;
  width: 100% !important;
}
.${PDC_ROOT} .pdc-contained-slider {
  margin-inline: 0 !important;
}
.${PDC_ROOT} .pdc-contained-slider > div > div {
  min-width: 0 !important;
  width: 100% !important;
}
html:root #QuickAccess-Menu .${PDC_ROOT} [data-pdc-focus-radius].gpfocus {
  border-radius: var(--pdc-focus-radius, 10px) !important;
}
.${PDC_ROOT} .pdc-dashboard-card > .pdc-dashboard-card-surface,
.${PDC_ROOT} .pdc-dashboard-card .pdc-dashboard-card-icon,
.${PDC_ROOT} .pdc-dashboard-card .pdc-dashboard-card-label,
.${PDC_ROOT} .pdc-dashboard-card .pdc-dashboard-card-description {
  transition: background-color 160ms ease-out,
              box-shadow 160ms ease-out,
              color 160ms ease-out,
              transform 160ms cubic-bezier(0.22, 1, 0.36, 1);
}
html:root #QuickAccess-Menu .${PDC_ROOT} .pdc-dashboard-card-focused,
html:root #QuickAccess-Menu .${PDC_ROOT} .pdc-dashboard-card.gpfocus {
  background: transparent !important;
  background-image: none !important;
  box-shadow: none !important;
  filter: none !important;
}
.${PDC_ROOT} .pdc-dashboard-card-focused > .pdc-dashboard-card-surface,
.${PDC_ROOT} .pdc-dashboard-card.gpfocus > .pdc-dashboard-card-surface {
  background: linear-gradient(rgba(0,0,0,0.08), rgba(0,0,0,0.18)), var(--pdc-card-accent) !important;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.28), 0 8px 20px rgba(0,0,0,0.28) !important;
}
.${PDC_ROOT} .pdc-dashboard-card-focused .pdc-dashboard-card-icon,
.${PDC_ROOT} .pdc-dashboard-card.gpfocus .pdc-dashboard-card-icon {
  background: rgba(0,0,0,0.18) !important;
  transform: scale(1.04);
}
.${PDC_ROOT} .pdc-dashboard-card-focused .pdc-dashboard-card-label,
.${PDC_ROOT} .pdc-dashboard-card.gpfocus .pdc-dashboard-card-label {
  color: rgba(255,255,255,0.98) !important;
}
.${PDC_ROOT} .pdc-dashboard-card-focused .pdc-dashboard-card-description,
.${PDC_ROOT} .pdc-dashboard-card.gpfocus .pdc-dashboard-card-description {
  color: rgba(255,255,255,0.78) !important;
}
@media (prefers-reduced-motion: reduce) {
  .${PDC_ROOT} .pdc-dashboard-card > .pdc-dashboard-card-surface,
  .${PDC_ROOT} .pdc-dashboard-card .pdc-dashboard-card-icon,
  .${PDC_ROOT} .pdc-dashboard-card .pdc-dashboard-card-label,
  .${PDC_ROOT} .pdc-dashboard-card .pdc-dashboard-card-description {
    transition: none !important;
  }
  .${PDC_ROOT} .pdc-dashboard-card-focused > .pdc-dashboard-card-surface,
  .${PDC_ROOT} .pdc-dashboard-card.gpfocus > .pdc-dashboard-card-surface,
  .${PDC_ROOT} .pdc-dashboard-card-focused .pdc-dashboard-card-icon,
  .${PDC_ROOT} .pdc-dashboard-card.gpfocus .pdc-dashboard-card-icon {
    transform: none;
  }
}
.${PDC_TABSTRIP} { scrollbar-width: none; -ms-overflow-style: none; }
.${PDC_TABSTRIP}::-webkit-scrollbar { display: none; width: 0; height: 0; }`.trim();
}

export function ensureFocusStyles(doc: Document = document): void {
  try {
    const css = buildFocusCss();
    const existing = doc.getElementById(FOCUS_STYLE_ID);
    if (existing) {
      if (existing.textContent !== css) existing.textContent = css;
      return;
    }
    const el = doc.createElement("style");
    el.id = FOCUS_STYLE_ID;
    el.textContent = css;
    doc.head.appendChild(el);
  } catch {
    /* best-effort */
  }
}
