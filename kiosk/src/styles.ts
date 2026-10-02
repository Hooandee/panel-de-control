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
.k-aurora { position: absolute; inset: 0; z-index: -1; pointer-events: none;
  background:
    radial-gradient(120% 80% at 0% -10%, rgba(var(--k-accent-rgb), .16), transparent 55%),
    radial-gradient(80% 60% at 110% 110%, rgba(var(--k-accent-rgb), .07), transparent 60%),
    linear-gradient(180deg, rgba(6,6,8,0) 40%, rgba(6,6,8,.55)); }

.k-header { display: flex; align-items: flex-end; justify-content: space-between; padding: 16px 20px 10px; }
.k-eyebrow { font-size: 9.5px; font-weight: 650; letter-spacing: .14em; text-transform: uppercase; color: var(--k-accent); }
.k-title { font-size: 26px; font-weight: 700; letter-spacing: -.03em; margin-top: 1px; animation: k-title-in .45s cubic-bezier(.2,.8,.2,1); }
@keyframes k-title-in { from { opacity: 0; transform: translateY(6px); filter: blur(4px); } }
.k-status { display: flex; align-items: center; gap: 12px; padding-bottom: 4px; color: ${color.textPrimary}; }
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
.k-reveal { animation: k-reveal .6s cubic-bezier(.2,.8,.2,1) both; animation-delay: calc(var(--i, 0) * 55ms); }
@keyframes k-reveal { from { opacity: 0; transform: translateY(10px) scale(.985); } }
.k-rings-caption { font-size: 9.5px; font-weight: 650; letter-spacing: .1em; text-transform: uppercase; color: ${color.textMuted}; }

.k-now { height: 100%; display: grid; gap: 12px; grid-template-columns: 1.3fr 1fr; grid-template-rows: minmax(0, 1.15fr) minmax(0, 1fr) 62px;
  grid-template-areas: "hero rings" "hero battery" "strip strip"; }
.k-hero { grid-area: hero; display: flex; flex-direction: column; justify-content: flex-end; padding: 18px; }
.k-hero-art { position: absolute; inset: 0; background-size: cover; background-position: center; opacity: 0;
  transition: opacity 1s ease; }
.k-hero-art.is-ready { opacity: 1; }
.k-hero-shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0,0,0,0) 30%, rgba(0,0,0,.25) 55%, rgba(0,0,0,.82)); }
.k-hero-foot { position: relative; display: flex; flex-direction: column; gap: 8px; }
.k-hero-logo { max-width: 82%; max-height: 74px; object-fit: contain; object-position: left bottom; filter: drop-shadow(0 4px 14px rgba(0,0,0,.6));
  animation: k-reveal .7s .15s cubic-bezier(.2,.8,.2,1) both; }
.k-hero-title { font-size: 24px; font-weight: 750; letter-spacing: -.03em; line-height: 1.05; text-shadow: 0 2px 16px rgba(0,0,0,.5); }
.k-hero-meta { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 550; color: rgba(255,255,255,.72); }
.k-live { width: 7px; height: 7px; border-radius: 4px; background: var(--k-ok); box-shadow: 0 0 8px rgba(126,224,160,.7); }
.k-fps { position: absolute; top: 14px; right: 14px; display: flex; align-items: baseline; gap: 4px; padding: 6px 11px; border-radius: 14px;
  background: rgba(0,0,0,.5); box-shadow: inset 0 0 0 .5px rgba(255,255,255,.14); }
.k-fps b { font-size: 18px; font-weight: 650; letter-spacing: -.02em; }
.k-fps span { font-size: 9px; font-weight: 700; letter-spacing: .1em; color: rgba(255,255,255,.6); }
.k-hero.is-idle { justify-content: center; padding: 22px 24px; isolation: isolate; }
.k-standby-time { font-size: 92px; font-weight: 200; letter-spacing: -.055em; line-height: .9;
  background: linear-gradient(180deg, #fff 30%, rgba(255,255,255,.62)); -webkit-background-clip: text; background-clip: text; color: transparent; }
.k-standby-date { margin-top: 12px; font-size: 14px; font-weight: 550; color: ${color.textMuted}; }
.k-standby-date::first-letter { text-transform: uppercase; }
.k-hero.is-idle::before { content: ""; position: absolute; inset: -40%; z-index: -1;
  background:
    radial-gradient(35% 35% at 30% 30%, rgba(var(--k-accent-rgb), .30), transparent 70%),
    radial-gradient(30% 30% at 70% 75%, rgba(var(--k-accent-rgb), .16), transparent 70%);
  }

.k-rings { grid-area: rings; display: flex; align-items: center; gap: 12px; padding: 12px 14px; }
.k-rings-dial { position: relative; flex: 0 0 auto; width: 132px; height: 132px; }
.k-rings-dial svg { width: 100%; height: 100%; overflow: visible; }
.k-ring-track { fill: none; stroke-width: 10; opacity: .16; }
.k-ring-bar { fill: none; stroke-width: 10; stroke-linecap: round;
  transition: stroke-dashoffset .8s cubic-bezier(.2,.8,.2,1); }
.k-rings-centre { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; }
.k-rings-centre b { font-size: 22px; font-weight: 300; letter-spacing: -.04em; line-height: 1; }
.k-legend { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 9px; }
.k-legend span { display: flex; flex-direction: column; font-size: 9.5px; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; color: ${color.textMuted};
  padding-left: 11px; position: relative; }
.k-legend span::before { content: ""; position: absolute; left: 0; top: 4px; width: 5px; height: 5px; border-radius: 3px; background: var(--c); }
.k-legend b { order: 2; font-size: 17px; font-weight: 600; letter-spacing: -.02em; text-transform: none; color: ${color.textPrimary}; }

.k-battery { grid-area: battery; display: flex; flex-direction: column; padding: 14px 16px; gap: 6px; }
.k-battery-top { display: flex; justify-content: space-between; align-items: center; }
.k-bolt { color: var(--k-ok); font-size: 13px; }
.k-battery-value { display: flex; align-items: baseline; gap: 2px; margin-top: auto; }
.k-battery-value b { font-size: 58px; font-weight: 250; letter-spacing: -.05em; line-height: .95; }
.k-battery-value span { font-size: 20px; font-weight: 500; color: ${color.textMuted}; }
.k-capsule { height: 8px; border-radius: 4px; background: rgba(255,255,255,.1); overflow: hidden; }
.k-capsule > div { height: 100%; border-radius: 4px; background: ${color.textPrimary}; transition: width 1s cubic-bezier(.2,.8,.2,1); }
.k-battery.is-charging .k-capsule > div, .k-battery.is-full .k-capsule > div { background: var(--k-ok); }
.k-battery.is-low .k-capsule > div { background: var(--k-danger); }
.k-battery-label { font-size: 11.5px; font-weight: 550; color: ${color.textMuted}; }

.k-strip { grid-area: strip; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.k-tile { border-radius: 20px; padding: 10px 14px; display: flex; flex-direction: column; justify-content: center; gap: 3px; }
.k-tile-value { display: flex; align-items: center; gap: 7px; min-width: 0; }
.k-tile-value b { font-size: 17px; font-weight: 600; letter-spacing: -.02em; }
.k-tile-value small { font-size: 10px; font-weight: 550; color: ${color.textMuted}; }
.k-tile-word { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.k-fan { width: 18px; height: 18px; flex: 0 0 auto; fill: none; stroke: ${color.textPrimary}; stroke-width: 1.7; }
.k-dot { width: 8px; height: 8px; flex: 0 0 auto; border-radius: 4px; background: rgba(255,255,255,.25); }
.k-dot.is-on { background: var(--k-ok); box-shadow: 0 0 10px rgba(126,224,160,.6); }

.k-page-error { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; padding: 18px; color: ${color.textMuted}; }

@media (prefers-reduced-motion: reduce) {
  .k-reveal, .k-title { animation: none !important; }
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
