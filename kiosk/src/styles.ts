import { theme } from "../../src/theme";

const { color, radius } = theme;

export const KIOSK_LOGICAL_WIDTH = 620;

export const KIOSK_CSS = `
html, body, #kiosk { height: 100%; margin: 0; }
html { background: ${color.surface}; color: ${color.textPrimary}; color-scheme: dark; }
body {
  font-family: Inter, "Noto Sans", system-ui, sans-serif;
  font-size: ${theme.font.body}px;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "tnum" 1;
  user-select: none;
  overflow: hidden;
}
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
button { font: inherit; color: inherit; }

.k-shell { position: relative; height: 100%; display: flex; flex-direction: column; overflow: hidden; isolation: isolate;
  --k-ok: ${color.ok}; --k-hot: ${color.boost}; --k-warn: ${color.warn}; --k-danger: ${color.danger};
  --k-glass: rgba(255,255,255,.055); --k-glass-edge: rgba(255,255,255,.09);
  --pdc-surface-raised: rgba(255,255,255,.055);
  background: ${color.surface}; }
.k-backdrop { position: absolute; inset: -60px; z-index: -2; background-size: cover; background-position: center;
  filter: blur(46px) saturate(1.5) brightness(.36); opacity: 0; transition: opacity 1.4s ease; will-change: opacity; }
.k-backdrop.is-on { opacity: 1; }
.k-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 20px 10px; }
.k-title { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 20px; font-weight: 650;
  letter-spacing: -.025em; animation: k-title-in .45s cubic-bezier(.2,.8,.2,1); }
@keyframes k-title-in { from { opacity: 0; transform: translateY(6px); filter: blur(4px); } }
.k-status { flex: 0 0 auto; display: flex; align-items: center; gap: 12px; color: ${color.textPrimary}; }
.k-clock { font-size: 15px; font-weight: 600; letter-spacing: -.01em; }
.k-status-battery { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: ${color.textMuted}; }
.k-status-shell { position: relative; width: 24px; height: 11.5px; border-radius: 3.5px; padding: 1.5px; box-shadow: inset 0 0 0 1px rgba(255,255,255,.38); }
.k-status-shell::after { content: ""; position: absolute; right: -3px; top: 3.75px; width: 1.5px; height: 4px; border-radius: 0 1px 1px 0; background: rgba(255,255,255,.38); }
.k-status-shell > span { display: block; height: 100%; border-radius: 2px; background: ${color.textPrimary}; transition: width .8s ease; }
.k-status-battery.is-charging .k-status-shell > span { background: var(--k-ok); }

.k-pager { flex: 1; min-height: 0; display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; scrollbar-width: none; overscroll-behavior: contain; }
.k-page { flex: 0 0 100%; min-height: 0; scroll-snap-align: start; overflow-y: auto; padding: 2px 16px 30px; scrollbar-width: none; }
.k-blocks { display: block !important; columns: 2; column-gap: 12px; }
.k-blocks > * { break-inside: avoid; margin: 0 0 12px !important; }

.k-dots { position: absolute; left: 0; right: 0; bottom: 10px; display: flex; justify-content: center; gap: 2px; }
.k-dots button { width: 22px; height: 16px; padding: 0; border: 0; background: none; display: grid; place-items: center; }
.k-dots button::before { content: ""; width: 6px; height: 6px; border-radius: 3px; background: rgba(255,255,255,.28);
  transition: width .4s cubic-bezier(.2,.8,.2,1), background .3s ease; }
.k-dots button.is-on::before { width: 18px; background: ${color.textPrimary}; }

.k-card { position: relative; overflow: hidden; border-radius: 24px; background: var(--k-glass);
  box-shadow: inset 0 0 0 .5px var(--k-glass-edge), 0 10px 30px rgba(0,0,0,.28); }

.d-deck { height: 100%; display: grid; gap: 12px; grid-template-columns: 148px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr) auto auto; grid-template-areas: "fader live" "fader fan" "fader toggles"; }
.d-section-label { font-size: 12px; font-weight: 500; color: ${color.textMuted}; }

.d-fader { grid-area: fader; position: relative; overflow: hidden; border-radius: 30px; touch-action: none;
  background: rgba(255,255,255,.08); box-shadow: inset 0 0 0 .5px rgba(255,255,255,.08); }
.d-fader-fill { position: absolute; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,.94);
  transition: height .22s cubic-bezier(.2,.8,.2,1); }
.d-fader.is-active .d-fader-fill { transition: none; }
.d-fader.is-locked .d-fader-fill { background: rgba(var(--k-accent-rgb), .55); }
.d-fader-top, .d-fader-caption { position: absolute; left: 0; right: 0; text-align: center; pointer-events: none; transition: color .2s ease; }
.d-fader-top { color: ${color.textPrimary}; }
.d-fader-caption { color: #15151a; }
.d-fader.is-full .d-fader-top { color: #15151a; }
.d-fader.is-locked .d-fader-caption, .d-fader.is-locked.is-full .d-fader-top { color: ${color.textPrimary}; }
.d-fader-top { top: 18px; display: flex; flex-direction: column; gap: 2px; }
.d-fader-top span { font-size: 12px; font-weight: 500; opacity: .75; }
.d-fader-top b { font-size: 54px; font-weight: 300; letter-spacing: -.05em; line-height: 1; }
.d-fader-caption { bottom: 16px; font-size: 11px; font-weight: 550; line-height: 1.35; padding: 0 8px; }

.d-live { grid-area: live; position: relative; display: flex; flex-direction: column; justify-content: space-between;
  min-height: 0; border-radius: 30px; padding: 16px 20px 14px; background: rgba(255,255,255,.06);
  box-shadow: inset 0 0 0 .5px rgba(255,255,255,.08); overflow: hidden; }
.d-live-main { display: flex; align-items: baseline; gap: 6px; }
.d-live-main b { font-size: 84px; font-weight: 250; letter-spacing: -.06em; line-height: .9; }
.d-live-main span { font-size: 18px; font-weight: 500; color: ${color.textMuted}; }
.d-spark { position: absolute; left: 0; right: 0; top: 44%; width: 100%; height: 26%; pointer-events: none; }
.d-spark-area { fill: url(#d-spark-fill); stroke: none; }
.d-spark-line { fill: none; stroke: var(--k-accent); stroke-width: 1.75; vector-effect: non-scaling-stroke; stroke-linejoin: round; stroke-linecap: round; opacity: .85; }
.d-live-stats { position: relative; display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; }
.d-live-stats div { display: flex; flex-direction: column; gap: 1px; }
.d-live-stats dt { font-size: 11.5px; font-weight: 500; color: ${color.textMuted}; }
.d-live-stats dd { margin: 0; font-size: 16px; font-weight: 600; letter-spacing: -.01em; }

.d-fan { grid-area: fan; display: flex; flex-direction: column; gap: 8px; border-radius: 24px; padding: 12px 14px;
  background: rgba(255,255,255,.06); box-shadow: inset 0 0 0 .5px rgba(255,255,255,.08); }
.d-segment { display: flex; gap: 4px; padding: 4px; border-radius: 16px; background: rgba(0,0,0,.35); }
.d-segment button { flex: 1; min-width: 0; border: 0; border-radius: 12px; padding: 10px 4px; background: transparent;
  font-size: 13px; font-weight: 550; color: ${color.textMuted}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background .25s ease, color .25s ease; }
.d-segment button.is-on { background: rgba(255,255,255,.16); color: ${color.textPrimary}; box-shadow: 0 1px 6px rgba(0,0,0,.3); }

.d-toggles { grid-area: toggles; display: grid; grid-template-columns: repeat(auto-fit, minmax(0, 1fr)); gap: 12px; }
.d-toggle { display: flex; align-items: center; gap: 10px; min-width: 0; border: 0; border-radius: 24px; padding: 12px;
  text-align: left; background: rgba(255,255,255,.06); box-shadow: inset 0 0 0 .5px rgba(255,255,255,.08);
  transition: transform .15s ease, background .25s ease; }
.d-toggle:active { transform: scale(.96); }
.d-toggle-icon { flex: 0 0 40px; height: 40px; border-radius: 20px; display: grid; place-items: center; background: rgba(255,255,255,.12);
  transition: background .25s ease; }
.d-toggle-icon svg { width: 20px; height: 20px; fill: none; stroke: ${color.textPrimary}; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.d-toggle.is-on .d-toggle-icon { background: var(--k-accent); }
.d-toggle.is-on .d-toggle-icon svg { stroke: ${color.onAccent}; }
.d-toggle-text { display: flex; flex-direction: column; min-width: 0; }
.d-toggle-text b { font-size: 14px; font-weight: 600; }
.d-toggle-text small { font-size: 11.5px; color: ${color.textMuted}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.k-page-error { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; padding: 18px; color: ${color.textMuted}; }

@media (prefers-reduced-motion: reduce) {
  .k-title { animation: none !important; }
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

.k-toasts { position: fixed; top: 12px; left: 0; right: 0; z-index: 30; display: flex; flex-direction: column; align-items: center; gap: 6px; pointer-events: none; }
.k-toast { display: flex; flex-direction: column; gap: 2px; max-width: 80%; padding: 10px 16px; border-radius: 18px;
  background: rgba(30,30,36,.96); box-shadow: 0 10px 30px rgba(0,0,0,.4); animation: k-rise .3s ease; }
.k-toast span { color: ${color.textMuted}; font-size: ${theme.font.caption}px; }
`;
