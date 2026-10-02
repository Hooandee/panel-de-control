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

.k-shell { position: relative; height: 100%; display: flex; flex-direction: column;
  background:
    radial-gradient(110% 70% at 0% 0%, rgba(var(--k-accent-rgb), .14), transparent 60%),
    radial-gradient(90% 60% at 100% 100%, rgba(var(--k-accent-rgb), .06), transparent 60%),
    ${color.surface}; }
.k-header { display: flex; align-items: flex-end; justify-content: space-between; padding: 14px 18px 8px; }
.k-eyebrow { font-size: 10px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--k-accent); }
.k-title { font-size: 22px; font-weight: 700; letter-spacing: -.02em; margin-top: 2px; }
.k-clock { font-size: 15px; font-weight: 600; color: ${color.textMuted}; }

.k-pager { flex: 1; display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; scrollbar-width: none; }
.k-page { flex: 0 0 100%; scroll-snap-align: start; overflow-y: auto; padding: 4px 14px 26px; scrollbar-width: none; }
.k-columns > div { display: block !important; columns: 2; column-gap: 10px; }
.k-columns > div > * { break-inside: avoid; margin-bottom: 10px; }

.k-dots { position: absolute; left: 0; right: 0; bottom: 8px; display: flex; justify-content: center; gap: 6px; pointer-events: none; }
.k-dots i { width: 6px; height: 6px; border-radius: 3px; background: rgba(255,255,255,.28); transition: all .35s cubic-bezier(.2,.8,.2,1); }
.k-dots i.is-on { width: 16px; background: ${color.textPrimary}; }

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
  background: rgba(30,30,36,.92); box-shadow: 0 10px 30px rgba(0,0,0,.4); backdrop-filter: blur(20px); animation: k-rise .3s ease; }
.k-toast span { color: ${color.textMuted}; font-size: ${theme.font.caption}px; }
`;
