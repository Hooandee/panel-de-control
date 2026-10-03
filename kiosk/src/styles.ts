import { theme } from "../../src/theme";

const { color, radius } = theme;

export const KIOSK_LOGICAL_WIDTH = 620;

// Glass is the default look. backdrop-filter only lives on the open dialog: Firefox paints the
// bottom screen in software, so anything always on screen stays a plain gradient.
export const KIOSK_CSS = `
html, body, #kiosk { height: 100%; margin: 0; }
html { background: #000; color: #fff; color-scheme: dark; }
body {
  font-family: Inter, "Noto Sans", system-ui, sans-serif;
  font-size: ${theme.font.body}px;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "tnum" 1, "cv11" 1, "ss01" 1;
  user-select: none;
  overflow: hidden;
}
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
button { font: inherit; color: inherit; background: none; border: 0; padding: 0; text-align: left; }
button:disabled { cursor: default; }

.k-shell { position: relative; height: 100%; overflow: hidden; isolation: isolate; background: #000;
  --k-accent: #0a84ff; --k-accent-rgb: 10,132,255; }
.k-error { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  color: rgba(255,255,255,.7); }
.k-asleep { position: fixed; inset: 0; z-index: 50; background: #000; }

.g-i { fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.g-i.is-spin { animation: g-spin 2.6s linear infinite; }
@keyframes g-spin { to { transform: rotate(360deg); } }

.h-head { position: absolute; left: 0; right: 0; top: 0; height: 200px; pointer-events: none; }
.h-banner { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: center 38%;
  opacity: 0; transition: opacity 1s ease; }
.h-banner.is-on { opacity: 1; }
.h-shade { position: absolute; inset: -1px 0; background: linear-gradient(180deg, rgba(0,0,0,.25) 0%, rgba(0,0,0,.05) 25%, rgba(0,0,0,.6) 55%, #000 88%, #000 100%); }
.h-top { position: absolute; left: 18px; right: 18px; top: 12px; display: flex; justify-content: space-between;
  font-size: 12px; font-weight: 550; text-shadow: 0 1px 8px rgba(0,0,0,.6); }
.h-top .is-charging { color: ${color.ok}; }
.h-game { position: absolute; left: 18px; top: 40px; width: 330px; height: 80px; display: flex; flex-direction: column; justify-content: flex-end; gap: 6px; }
.h-logo { max-height: 58px; max-width: 200px; object-fit: contain; object-position: left bottom; align-self: flex-start;
  filter: drop-shadow(0 6px 18px rgba(0,0,0,.65)); opacity: 0; transition: opacity .6s ease; }
.h-logo.is-on { opacity: 1; }
.h-logo.is-on + .h-name { display: none; }
.h-name { font-size: 24px; font-weight: 650; letter-spacing: -.03em; line-height: 1.05; text-shadow: 0 2px 14px rgba(0,0,0,.7);
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.h-session { font-size: 12px; font-weight: 500; color: rgba(255,255,255,.75); text-shadow: 0 1px 8px rgba(0,0,0,.7); }
.h-stats { position: absolute; right: 18px; top: 46px; display: flex; align-items: flex-start; gap: 22px; text-align: right; }
.h-temp { padding-top: 14px; }
.h-temp b { font-size: 36px; font-weight: 250; letter-spacing: -.04em; line-height: .85; text-shadow: 0 2px 20px rgba(0,0,0,.45); }
.h-temp small { display: block; margin-top: 6px; font-size: 12px; font-weight: 500; color: rgba(255,255,255,.7); }
.h-fps b { font-size: 66px; font-weight: 200; letter-spacing: -.06em; line-height: .85; text-shadow: 0 2px 20px rgba(0,0,0,.45); }
.h-fps small { display: block; font-size: 12px; font-weight: 500; color: rgba(255,255,255,.7); }
.h-pace { position: absolute; left: 18px; right: 18px; top: 128px; width: calc(100% - 36px); height: 22px; }
.h-pace path { fill: none; stroke: rgba(255,255,255,.6); stroke-width: 1.3; vector-effect: non-scaling-stroke; }
.h-pace line { stroke: rgba(255,255,255,.18); stroke-width: 1; stroke-dasharray: 2 3; vector-effect: non-scaling-stroke; }

.t-grid { position: absolute; left: 14px; right: 14px; top: 160px; bottom: 16px; display: grid; gap: 9px;
  grid-template-columns: repeat(6, minmax(0, 1fr)); grid-template-rows: repeat(3, minmax(0, 1fr));
  grid-template-areas: "perf perf fps fan bri vol" "perf perf rgb rgb bri vol" "hz turbo shot kbd qam off"; }
.t-tile { position: relative; min-width: 0; min-height: 0; border-radius: 24px; overflow: hidden; display: flex; flex-direction: column;
  justify-content: space-between; padding: 12px;
  background: linear-gradient(160deg, rgba(255,255,255,.13), rgba(255,255,255,.05));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.22), inset 0 0 0 .5px rgba(255,255,255,.08);
  transition: transform .2s cubic-bezier(.2,1.4,.4,1), background .25s, opacity .25s; }
.t-tile:active:not(:disabled) { transform: scale(.95); }
.t-tile:disabled { opacity: .45; }
.t-label { font-size: 12px; font-weight: 600; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.t-sub { font-size: 11px; color: rgba(255,255,255,.6); line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.t-icon { width: 34px; height: 34px; border-radius: 17px; display: grid; place-items: center; background: rgba(255,255,255,.14);
  transition: background .25s, color .25s; }
.t-icon svg { width: 18px; height: 18px; }
.t-tile.is-on .t-icon { background: #fff; color: #111; }
.t-tile.is-small { align-items: center; justify-content: center; gap: 7px; padding: 8px; text-align: center; }
.t-tile.is-small .t-label { font-size: 11px; font-weight: 550; }
.t-big { font-size: 24px; font-weight: 350; letter-spacing: -.03em; line-height: 1; }

.t-perf { grid-area: perf; padding: 16px; }
.t-level { display: flex; align-items: baseline; gap: 6px; }
.t-level b { font-size: 64px; font-weight: 200; letter-spacing: -.06em; line-height: .85; }
.t-level span { font-size: 14px; color: rgba(255,255,255,.6); }
.t-perf-name { font-size: 16px; font-weight: 600; margin-top: 4px; }
.t-perf-detail { font-size: 11.5px; color: rgba(255,255,255,.6); margin-top: 2px; }
.t-mini { display: flex; gap: 4px; }
.t-mini i { flex: 1; height: 6px; border-radius: 3px; background: rgba(255,255,255,.16); transition: background .25s; }
.t-mini i.is-on { background: #fff; }

.t-fps { grid-area: fps; } .t-fan { grid-area: fan; } .t-hz { grid-area: hz; } .t-turbo { grid-area: turbo; }
.t-shot { grid-area: shot; } .t-kbd { grid-area: kbd; } .t-qam { grid-area: qam; } .t-off { grid-area: off; }
.t-bri { grid-area: bri; } .t-vol { grid-area: vol; }

.t-rgb { grid-area: rgb; padding: 12px 14px; }
.t-row { display: flex; justify-content: space-between; align-items: flex-end; gap: 8px; }
.t-strip { height: 14px; border-radius: 7px; transition: background .4s, opacity .3s; }
.t-strip.is-off { background: rgba(255,255,255,.12); }

.g-vfader { position: relative; min-height: 0; border-radius: 24px; overflow: hidden; touch-action: none;
  background: rgba(255,255,255,.12); box-shadow: inset 0 1px 0 rgba(255,255,255,.2); }
.g-vfader.is-off { opacity: .45; }
.g-vfader-fill { position: absolute; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,.95);
  transition: height .18s cubic-bezier(.2,.8,.2,1); }
.g-vfader.is-drag .g-vfader-fill { transition: none; }
.g-vfader > svg { position: absolute; left: 50%; bottom: 16px; width: 24px; height: 24px; margin-left: -12px; stroke: #8e8e93; stroke-width: 1.9; }

.g-scrim { position: absolute; inset: 0; z-index: 10; background: rgba(0,0,0,.3); opacity: 0; transition: opacity .35s ease; }
.g-scrim.is-on { opacity: 1; }
.g-glass { position: absolute; z-index: 11; left: 50%; top: 50%; width: 560px; margin-left: -280px; border-radius: 38px; padding: 22px 24px 24px;
  background: linear-gradient(145deg, rgba(255,255,255,.20), rgba(255,255,255,.06) 42%, rgba(255,255,255,.10));
  backdrop-filter: blur(34px) saturate(190%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.55), inset 0 -1px 0 rgba(255,255,255,.08), inset 1px 0 0 rgba(255,255,255,.18),
    inset -1px 0 0 rgba(255,255,255,.10), 0 30px 80px rgba(0,0,0,.55);
  opacity: 0; transform: translateY(-46%) scale(.86); pointer-events: none;
  transition: opacity .28s ease, transform .5s cubic-bezier(.18,1.25,.4,1); }
.g-glass::before { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: radial-gradient(120% 60% at 15% 0%, rgba(255,255,255,.22), transparent 55%); }
.g-glass.is-on { opacity: 1; transform: translateY(-50%); pointer-events: auto; }
.g-hero { position: relative; display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
.g-bubble { width: 70px; height: 70px; flex: 0 0 70px; border-radius: 35px; display: grid; place-items: center;
  background: rgba(255,255,255,.14); box-shadow: inset 0 1px 0 rgba(255,255,255,.4); }
.g-bubble svg { width: 38px; height: 38px; stroke-width: 1.3; }
.g-bubble-num { font-size: 36px; font-weight: 250; letter-spacing: -.04em; }
.g-hero b { display: block; font-size: 38px; font-weight: 220; letter-spacing: -.05em; line-height: 1; }
.g-hero span { display: block; margin-top: 5px; font-size: 12.5px; color: rgba(255,255,255,.7); }
.g-orbs { position: relative; display: flex; justify-content: space-around; gap: 8px; }
.g-orbs.is-scroll { justify-content: flex-start; overflow-x: auto; scrollbar-width: none; margin: 0 -24px; padding: 2px 24px 4px; gap: 14px; }
.g-orb { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 74px; text-align: center;
  font-size: 12px; font-weight: 550; color: rgba(255,255,255,.85); }
.g-orb i { width: 66px; height: 66px; border-radius: 33px; display: grid; place-items: center; font-style: normal; font-size: 22px; font-weight: 450;
  background: rgba(255,255,255,.12); box-shadow: inset 0 1px 0 rgba(255,255,255,.45), inset 0 -1px 0 rgba(255,255,255,.06), 0 6px 18px rgba(0,0,0,.25);
  transition: background .3s, color .3s, transform .25s cubic-bezier(.2,1.4,.4,1); }
.g-orb i svg { width: 28px; height: 28px; stroke-width: 1.6; }
.g-orb:active:not(:disabled) i { transform: scale(.92); }
.g-orb.is-on i { background: rgba(255,255,255,.95); color: #111; }
.g-orb:disabled { opacity: .4; }
.g-glass.is-on .g-orb { animation: g-pop .5s cubic-bezier(.18,1.3,.4,1) both; }
.g-glass.is-on .g-orb:nth-child(2) { animation-delay: .03s; } .g-glass.is-on .g-orb:nth-child(3) { animation-delay: .06s; }
.g-glass.is-on .g-orb:nth-child(4) { animation-delay: .09s; } .g-glass.is-on .g-orb:nth-child(5) { animation-delay: .12s; }
.g-glass.is-on .g-orb:nth-child(n+6) { animation-delay: .15s; }
@keyframes g-pop { from { opacity: 0; transform: translateY(14px) scale(.9); } }
.g-note { position: relative; margin-top: 14px; text-align: center; font-size: 12px; line-height: 1.4; color: rgba(255,255,255,.6); }
.g-hbar { position: relative; height: 40px; border-radius: 13px; overflow: hidden; background: rgba(255,255,255,.14); margin-top: 14px; touch-action: none; }
.g-hbar.is-off { opacity: .45; }
.g-hbar-fill { position: absolute; left: 0; top: 0; bottom: 0; background: rgba(255,255,255,.95); }
.g-hbar > svg { position: absolute; left: 13px; top: 50%; width: 20px; height: 20px; margin-top: -10px; stroke: #1c1c1e; stroke-width: 1.9; }
.g-hbar-pct { position: absolute; right: 13px; top: 50%; margin-top: -9px; font-size: 13px; font-weight: 600; color: rgba(255,255,255,.75); mix-blend-mode: difference; }
.g-steps { position: relative; height: 30px; margin: 16px 6px 0; touch-action: none; }
.g-steps.is-off { opacity: .4; }
.g-steps-track { position: absolute; left: 11px; right: 11px; top: 9px; height: 8px; border-radius: 4px; background: rgba(255,255,255,.16); }
.g-steps-fill { position: absolute; left: 11px; top: 9px; height: 8px; border-radius: 4px; background: rgba(255,255,255,.95); transition: width .2s; }
.g-steps-knob { position: absolute; top: 0; width: 26px; height: 26px; margin-left: -13px; border-radius: 13px; background: #fff;
  box-shadow: 0 2px 12px rgba(0,0,0,.5); transition: left .2s; }
.g-steps.is-drag .g-steps-knob, .g-steps.is-drag .g-steps-fill { transition: none; }
.g-chips { position: relative; display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.g-chips button { padding: 8px 13px; border-radius: 16px; font-size: 12.5px; font-weight: 550; background: rgba(255,255,255,.12);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.25); transition: background .25s, color .25s; }
.g-chips button.is-on { background: rgba(255,255,255,.95); color: #111; }
.g-colors { position: relative; display: flex; justify-content: center; gap: 12px; margin-top: 14px; }
.g-colors button { width: 34px; height: 34px; border-radius: 17px; box-shadow: inset 0 0 0 1px rgba(255,255,255,.35), 0 4px 12px rgba(0,0,0,.3);
  transition: box-shadow .25s; }
.g-colors button.is-on { box-shadow: 0 0 0 3px rgba(255,255,255,.95); }
.g-cta { position: relative; display: block; margin: 18px auto 0; padding: 13px 26px; border-radius: 22px; background: #fff; color: #111;
  font-size: 15px; font-weight: 650; text-align: center; }
.g-cta:disabled { opacity: .6; }

@media (prefers-reduced-motion: reduce) {
  .g-i.is-spin, .g-glass.is-on .g-orb { animation: none !important; }
}

.k-section { display: flex; flex-direction: column; gap: 6px; }
.k-section-title { font-size: ${theme.font.caption}px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: ${color.textMuted}; padding: 4px 2px; }
.k-row { display: block; }
.k-item { padding: 10px 2px; }
.k-item.is-disabled { opacity: .45; }
.k-item-head { display: flex; align-items: center; gap: 10px; min-height: 30px; }
.k-item-icon { display: inline-flex; color: var(--k-accent); }
.k-item-text { flex: 1; min-width: 0; }
.k-item-label { font-weight: 600; }
.k-item-desc { font-size: ${theme.font.caption}px; color: ${color.textMuted}; margin-top: 2px; line-height: 1.35; }
.k-value { font-weight: 600; color: ${color.textMuted}; }

.k-switch { position: relative; flex: 0 0 auto; width: 46px; height: 28px; border: 0; border-radius: 14px; padding: 0;
  background: rgba(255,255,255,.16); transition: background .25s ease; }
.k-switch span { position: absolute; top: 2px; left: 2px; width: 24px; height: 24px; border-radius: 12px; background: #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,.35); transition: transform .28s cubic-bezier(.2,.8,.2,1); }
.k-switch.is-on { background: var(--k-accent); }
.k-switch.is-on span { transform: translateX(18px); }
.k-switch:disabled { opacity: .4; }

.k-range { -webkit-appearance: none; appearance: none; width: 100%; height: 28px; margin: 6px 0 0; background: transparent; touch-action: none; }
.k-range::-moz-range-track { height: 6px; border-radius: 3px; background: rgba(255,255,255,.14); }
.k-range::-moz-range-progress { height: 6px; border-radius: 3px; background: var(--k-accent); }
.k-range::-moz-range-thumb { width: 24px; height: 24px; border: 0; border-radius: 12px; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.4); }
.k-range::-webkit-slider-runnable-track { height: 6px; border-radius: 3px;
  background: linear-gradient(90deg, var(--k-accent) var(--fill), rgba(255,255,255,.14) var(--fill)); }
.k-range::-webkit-slider-thumb { -webkit-appearance: none; width: 24px; height: 24px; margin-top: -9px; border-radius: 12px; background: #fff; }
.k-notches { display: flex; justify-content: space-between; font-size: 10px; color: ${color.textMuted}; padding: 0 4px; }

.k-button { border: 0; border-radius: ${radius.sm + 4}px; padding: 10px 14px; font-weight: 600;
  background: rgba(255,255,255,.1); transition: transform .15s ease, background .2s ease; }
.k-button:active { transform: scale(.97); background: rgba(255,255,255,.16); }
.k-button.is-primary { background: var(--k-accent); color: ${color.onAccent}; }
.k-button:disabled { opacity: .4; }
.k-button-wide { width: 100%; }

.k-dropdown { display: inline-flex; align-items: center; gap: 8px; border: 0; border-radius: ${radius.sm + 2}px; padding: 8px 12px;
  background: rgba(255,255,255,.1); font-weight: 600; max-width: 100%; }
.k-chevron { color: ${color.textMuted}; }
.k-text { display: flex; flex-direction: column; gap: 4px; padding: 6px 2px; }
.k-text-row { display: flex; gap: 6px; }
.k-text input { flex: 1; min-width: 0; border: 0; border-radius: ${radius.sm + 2}px; padding: 10px 12px; font: inherit; color: inherit;
  background: rgba(255,255,255,.08); outline: none; }

.k-spinner { display: inline-block; width: 18px; height: 18px; border-radius: 50%; border: 2px solid rgba(255,255,255,.2);
  border-top-color: var(--k-accent); animation: k-spin .8s linear infinite; }
@keyframes k-spin { to { transform: rotate(360deg); } }

.k-modal-backdrop { position: fixed; inset: 0; z-index: 20; display: grid; place-items: center; padding: 18px;
  background: rgba(0,0,0,.5); backdrop-filter: blur(14px); animation: k-fade .2s ease; }
.k-modal { width: min(560px, 100%); max-height: 100%; overflow-y: auto; border-radius: ${radius.lg + 4}px; padding: 16px;
  background: rgba(22,22,28,.92); box-shadow: inset 0 0 0 .5px rgba(255,255,255,.12), 0 20px 60px rgba(0,0,0,.5);
  animation: k-rise .28s cubic-bezier(.2,.8,.2,1); }
.k-modal-root { position: relative; }
.k-modal-close { position: absolute; top: -6px; right: -6px; width: 30px; height: 30px; border: 0; border-radius: 15px;
  background: rgba(255,255,255,.1); font-size: 18px; line-height: 1; }
.k-modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.k-menu { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
.k-menu-item { text-align: left; border: 0; border-radius: ${radius.sm + 2}px; padding: 12px; background: transparent; font-weight: 500; }
.k-menu-item.is-selected { background: rgba(var(--k-accent-rgb), .18); color: var(--k-accent); }
@keyframes k-fade { from { opacity: 0; } }
@keyframes k-rise { from { opacity: 0; transform: translateY(14px) scale(.98); } }

.k-toasts { position: fixed; top: 34px; left: 0; right: 0; z-index: 30; display: flex; flex-direction: column; align-items: center; gap: 6px; pointer-events: none; }
.k-toast { display: flex; flex-direction: column; gap: 2px; max-width: 80%; padding: 10px 16px; border-radius: 18px;
  background: rgba(30,30,36,.96); box-shadow: 0 10px 30px rgba(0,0,0,.4); animation: k-rise .3s ease; }
.k-toast span { color: ${color.textMuted}; font-size: ${theme.font.caption}px; }
`;
