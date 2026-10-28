import type { ReactNode } from "react";

/** Small, layered silhouettes: all motion stays inside the fixed 48-unit canvas. */
export function SectionGlyph({ id, fallback }: { id: string; fallback: ReactNode }) {
  const art: Record<string, ReactNode> = {
    power: <><path opacity=".22" d="M27 3 8 27h13l-2 18 21-27H27Z"/><path className="pdc-glyph-pulse" fill="currentColor" stroke="none" d="m27 5-17 23h13l-2 15 18-23H26Z"/></>,
    system: <><rect x="12" y="12" width="24" height="24" rx="6" fill="currentColor" opacity=".2"/><path d="M17 5v7m14-7v7M17 36v7m14-7v7M5 17h7m-7 14h7m24-14h7m-7 14h7"/><rect x="12" y="12" width="24" height="24" rx="6"/><path className="pdc-glyph-scan" d="M19 24h10"/></>,
    display: <><rect x="5" y="8" width="38" height="27" rx="5" fill="currentColor" opacity=".15"/><rect x="5" y="8" width="38" height="27" rx="5"/><path d="M24 35v6m-9 0h18"/><path className="pdc-glyph-scan" d="m14 25 9-10m1 12 8-9"/></>,
    fans: <><circle cx="24" cy="24" r="20" opacity=".3"/><g className="pdc-glyph-spin" fill="currentColor" stroke="none"><path d="M24 22C8 22 8 9 18 7c8-2 12 7 6 15Zm2 2c0-16 13-16 15-6 2 8-7 12-15 6Zm-2 2c16 0 16 13 6 15-8 2-12-7-6-15Zm-2-2c0 16-13 16-15 6-2-8 7-12 15-6Z"/></g><circle cx="24" cy="24" r="4" fill="currentColor"/></>,
    audio: <><path fill="currentColor" stroke="none" d="M5 18h8L25 8v32L13 30H5Z"/><g className="pdc-glyph-wave"><path d="M31 16c5 4 5 12 0 16m6-22c9 8 9 20 0 28"/></g></>,
    hud: <><rect x="5" y="7" width="38" height="34" rx="6" opacity=".4"/><path d="M12 33h24"/><g className="pdc-glyph-bars" fill="currentColor" stroke="none"><rect x="12" y="23" width="5" height="10" rx="2"/><rect x="22" y="17" width="5" height="16" rx="2"/><rect x="32" y="12" width="5" height="21" rx="2"/></g></>,
    params: <><rect x="4" y="7" width="40" height="34" rx="6" fill="currentColor" opacity=".15"/><rect x="4" y="7" width="40" height="34" rx="6"/><path d="M5 15h38" opacity=".6"/><circle cx="10" cy="11" r="1" fill="currentColor" stroke="none"/><path d="m12 22 6 5-6 5" strokeWidth="3.5"/><path className="pdc-glyph-scan" d="M24 32h11" strokeWidth="3.5"/></>,
    cleaner: <><path d="m8 10-4 21v6a5 5 0 0 0 5 5h30a5 5 0 0 0 5-5v-6l-4-21Z" fill="currentColor" opacity=".18"/><path d="M26 10H10L5 30v7a4 4 0 0 0 4 4h30a4 4 0 0 0 4-4v-7l-2-9M5 30h38"/><circle cx="35" cy="35" r="2" fill="currentColor" stroke="none"/><path className="pdc-glyph-pulse" fill="currentColor" stroke="none" d="m35 3 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z"/></>,
    ambient: <><rect x="4" y="6" width="40" height="36" rx="6" fill="currentColor" opacity=".12"/><rect x="4" y="6" width="40" height="36" rx="6"/><path fill="currentColor" stroke="none" d="m6 36 12-16 10 12 6-7 8 11v4H6Z"/><g className="pdc-glyph-wave"><circle cx="33" cy="17" r="5" fill="currentColor" stroke="none"/></g></>,
    themes: <><path fill="currentColor" opacity=".3" d="M24 5C-2 5-1 42 20 42c11 0-1-10 7-10h8C50 32 48 5 24 5Z"/><path d="M24 5C-2 5-1 42 20 42c11 0-1-10 7-10h8C50 32 48 5 24 5Z"/><g className="pdc-glyph-pulse" fill="currentColor" stroke="none"><circle cx="14" cy="17" r="3"/><circle cx="25" cy="12" r="3"/><circle cx="35" cy="20" r="3"/></g></>,
    settings: <><g className="pdc-glyph-turn"><path d="M24 5v7m0 24v7M5 24h7m24 0h7M11 11l5 5m16 16 5 5M11 37l5-5m16-16 5-5" strokeWidth="6"/><circle cx="24" cy="24" r="13" fill="currentColor" opacity=".3"/><circle cx="24" cy="24" r="13"/></g><circle cx="24" cy="24" r="5"/></>,
    mandos: <><path d="M15 12h18c8 0 14 25 8 27-4 2-8-7-12-7H19c-4 0-8 9-12 7-6-2 0-27 8-27Z" fill="currentColor" opacity=".25"/><path d="M15 12h18c8 0 14 25 8 27-4 2-8-7-12-7H19c-4 0-8 9-12 7-6-2 0-27 8-27Z"/><path d="M15 19v10m-5-5h10"/><g className="pdc-glyph-pulse" fill="currentColor"><circle cx="33" cy="20" r="2"/><circle cx="37" cy="27" r="2"/></g></>,
  };
  const glyph = art[id];
  return glyph ? <svg className="pdc-section-glyph" viewBox="0 0 48 48" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{glyph}</svg> : <>{fallback}</>;
}

export const sectionGlyphStyles = `
.pdc-section-glyph { width:76%; height:76%; overflow:visible; }
.pdc-section-glyph g, .pdc-section-glyph path { transform-origin:24px 24px; }
.pdc-dashboard-card:is(:hover,:focus-within,.gpfocus,.pdc-dashboard-card-focused) .pdc-glyph-spin { animation:pdc-glyph-spin 720ms cubic-bezier(.2,.8,.2,1) both; }
.pdc-dashboard-card:is(:hover,:focus-within,.gpfocus,.pdc-dashboard-card-focused) .pdc-glyph-turn { animation:pdc-glyph-turn 540ms ease-out both; }
.pdc-dashboard-card:is(:hover,:focus-within,.gpfocus,.pdc-dashboard-card-focused) .pdc-glyph-pulse { animation:pdc-glyph-pulse 480ms ease-out both; }
.pdc-dashboard-card:is(:hover,:focus-within,.gpfocus,.pdc-dashboard-card-focused) .pdc-glyph-wave { animation:pdc-glyph-wave 580ms ease-out both; }
.pdc-dashboard-card:is(:hover,:focus-within,.gpfocus,.pdc-dashboard-card-focused) .pdc-glyph-scan { animation:pdc-glyph-scan 520ms ease-out both; }
.pdc-dashboard-card:is(:hover,:focus-within,.gpfocus,.pdc-dashboard-card-focused) .pdc-glyph-bars { animation:pdc-glyph-bars 520ms ease-out both; transform-origin:24px 34px; }
@keyframes pdc-glyph-spin { from{transform:rotate(-150deg)} to{transform:rotate(0)} }
@keyframes pdc-glyph-turn { 0%{transform:rotate(-35deg)} 70%{transform:rotate(5deg)} 100%{transform:rotate(0)} }
@keyframes pdc-glyph-pulse { 0%{opacity:.4;transform:scale(.8)} 55%{opacity:1;transform:scale(1.08)} 100%{transform:scale(1)} }
@keyframes pdc-glyph-wave { 0%{opacity:.2;transform:scale(.8)} 65%{opacity:1;transform:scale(1.06)} 100%{transform:scale(1)} }
@keyframes pdc-glyph-scan { 0%{opacity:.2;transform:translateY(4px)} 100%{opacity:1;transform:translateY(0)} }
@keyframes pdc-glyph-bars { 0%{transform:scaleY(.35)} 70%{transform:scaleY(1.08)} 100%{transform:scaleY(1)} }
@media(prefers-reduced-motion:reduce){.pdc-dashboard-card .pdc-section-glyph *{animation:none!important}}
`;
