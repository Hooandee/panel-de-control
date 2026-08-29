export const ORBITAL_ABYSS_CSS = `
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-active="true"] {
  --pdc-orbit-cyan: #62f7ff;
  --pdc-orbit-magenta: #ff38bd;
  --pdc-orbit-violet: #8d61ff;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-active="true"] [data-pdc-orbit-viewport="true"] {
  background: #010104 !important;
  contain: none !important;
  height: 100vh !important;
  inset: 0 !important;
  isolation: isolate;
  overflow: visible !important;
  pointer-events: none !important;
  position: fixed !important;
  transform: none !important;
  width: 100vw !important;
  z-index: 9000 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-active="true"] #header {
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
  visibility: hidden !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-footer="true"] {
  opacity: 0 !important;
  pointer-events: none !important;
  visibility: hidden !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-active="true"] #pdc-obsidian-bloom-stage,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-active="true"] [data-pdc-orbit-suppressed="true"] {
  display: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-active="true"] #Main[data-pdc-orbit-main="true"] .ReactVirtualized__Grid:not([data-pdc-orbit-viewport="true"]) {
  display: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #pdc-orbital-abyss {
  background:
    radial-gradient(circle at 50% 46%, rgba(53,26,102,.34), transparent 17%),
    radial-gradient(circle at 18% 16%, rgba(66,245,255,.16), transparent 28%),
    radial-gradient(circle at 86% 78%, rgba(255,47,177,.16), transparent 31%),
    linear-gradient(180deg, #010105, #070412 55%, #010103);
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  position: fixed;
  z-index: 0;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #pdc-orbital-abyss::before {
  background-image:
    radial-gradient(circle, rgba(255,255,255,.8) 0 1px, transparent 1.6px),
    radial-gradient(circle, rgba(98,247,255,.56) 0 1px, transparent 1.8px);
  background-position: 0 0, 37px 29px;
  background-size: 73px 73px, 109px 109px;
  content: "";
  inset: 0;
  mask-image: linear-gradient(180deg, rgba(0,0,0,.72), transparent 74%);
  opacity: .34;
  position: absolute;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #pdc-orbital-abyss [data-pdc-orbit-ring] {
  border: 1px solid rgba(98,247,255,.18);
  border-radius: 50%;
  box-shadow:
    0 0 28px rgba(98,247,255,.08),
    inset 0 0 34px rgba(255,56,189,.05);
  height: 60vh;
  left: 50%;
  position: absolute;
  top: 45%;
  transform: translate3d(-50%,-50%,0) perspective(760px) rotateX(68deg) rotateZ(var(--pdc-orbit-phase));
  transition: transform 680ms cubic-bezier(.14,.84,.18,1);
  width: 76vw;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #pdc-orbital-abyss [data-pdc-orbit-ring="1"] {
  border-color: rgba(255,56,189,.17);
  height: 52vh;
  transform: translate3d(-50%,-50%,0) perspective(760px) rotateX(68deg) rotateZ(var(--pdc-orbit-phase-reverse));
  width: 66vw;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #pdc-orbital-abyss [data-pdc-orbit-ring="2"] {
  border-color: rgba(141,97,255,.2);
  height: 43vh;
  transform: translate3d(-50%,-50%,0) perspective(760px) rotateX(68deg) rotateZ(var(--pdc-orbit-phase-offset));
  width: 55vw;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #pdc-orbital-abyss [data-pdc-orbit-horizon] {
  background: radial-gradient(ellipse, rgba(98,247,255,.2), rgba(255,56,189,.08) 38%, transparent 70%);
  height: 22vh;
  left: 50%;
  position: absolute;
  top: 45%;
  transform: translate3d(-50%,-50%,0);
  width: 62vw;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption="true"] {
  bottom: 5.5%;
  left: 50%;
  position: absolute;
  text-align: center;
  transform: translate3d(-50%,0,0);
  width: min(72vw,720px);
  z-index: 4;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-title="true"] {
  align-items: center;
  color: rgba(249,252,255,.98);
  display: flex;
  font-family: "PDC Oxanium", "Motiva Sans", sans-serif;
  font-size: clamp(18px,2.15vw,26px);
  font-weight: 600;
  gap: 10px;
  justify-content: center;
  letter-spacing: .08em;
  line-height: 1.15;
  overflow-wrap: anywhere;
  text-align: center !important;
  text-shadow:
    -10px 0 28px rgba(255,56,189,.46),
    10px 0 28px rgba(98,247,255,.52),
    0 2px 14px rgba(0,0,0,.9);
  text-transform: uppercase;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-label="true"] {
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  display: -webkit-box;
  min-width: 0;
  overflow: hidden;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-icon="true"] {
  color: var(--pdc-orbit-cyan);
  flex: 0 0 auto;
  filter: drop-shadow(0 0 8px rgba(98,247,255,.5));
  height: clamp(22px,2.35vw,28px);
  overflow: visible;
  width: clamp(22px,2.35vw,28px);
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-icon="true"][hidden] {
  display: none;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-icon-frame="true"] {
  fill: rgba(5,10,18,.9);
  stroke: currentColor;
  stroke-width: 1.35;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-icon-glyph="true"] {
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-action="play"] [data-pdc-orbit-caption-icon-glyph="true"] {
  fill: currentColor;
  stroke: none;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] #pdc-orbital-abyss [data-pdc-orbit-caption-meta="true"] {
  color: rgba(196,231,240,.7);
  font-family: "Roboto-Mono", "Motiva Sans", sans-serif;
  font-size: clamp(10px,1vw,13px);
  font-weight: 600;
  letter-spacing: .15em;
  margin-top: 7px;
  text-align: center !important;
  text-transform: uppercase;
}
html[data-pdc-theme-runtime="obsidian-bloom"] [data-pdc-orbit-list="true"] {
  contain: none !important;
  height: 100vh !important;
  inset: 0 !important;
  max-height: none !important;
  min-height: 100vh !important;
  overflow: visible !important;
  pointer-events: none !important;
  position: absolute !important;
  transform: none !important;
  width: 100vw !important;
  z-index: 2 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"] [data-pdc-orbit-card="true"] {
  filter: none !important;
  inset: auto !important;
  left: var(--pdc-orbit-x,50%) !important;
  margin: 0 !important;
  opacity: var(--pdc-orbit-opacity,0) !important;
  pointer-events: auto !important;
  position: absolute !important;
  top: var(--pdc-orbit-y,45%) !important;
  transform: translate3d(-50%,-50%,0) perspective(980px) rotateY(var(--pdc-orbit-tilt,0deg)) rotateZ(var(--pdc-orbit-roll,0deg)) scale(var(--pdc-orbit-scale,.5)) !important;
  transform-origin: center !important;
  transition:
    left 620ms cubic-bezier(.14,.84,.18,1),
    top 620ms cubic-bezier(.14,.84,.18,1),
    transform 620ms cubic-bezier(.14,.84,.18,1),
    opacity 360ms ease !important;
  will-change: left, top, transform;
  z-index: var(--pdc-orbit-z,1) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-orbit-restoring="true"] [data-pdc-orbit-card="true"] {
  transition: none !important;
  will-change: auto;
}
html[data-pdc-theme-runtime="obsidian-bloom"] [data-pdc-orbit-visible="false"] {
  opacity: 0 !important;
  pointer-events: none !important;
  visibility: hidden !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-card="true"] [role="link"] {
  border-radius: 18px !important;
  overflow: hidden !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-card="true"] [role="link"] img {
  border-radius: inherit !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-native-copy="true"] {
  opacity: 0 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-selected="true"] [data-pdc-orbit-native-action="true"] {
  display: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"] [data-pdc-orbit-selected="true"] {
  filter: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-selected="true"].gpfocus,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-selected="true"] .gpfocus {
  border-radius: 20px !important;
  box-shadow:
    0 0 0 1px rgba(255,255,255,.86),
    0 0 0 4px rgba(98,247,255,.56),
    -24px 0 62px rgba(255,56,189,.34),
    24px 0 62px rgba(98,247,255,.4),
    0 30px 76px rgba(0,0,0,.82) !important;
  outline: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"] [data-pdc-orbit-selected="true"] img {
  border-radius: 18px !important;
  box-shadow:
    0 0 0 1px rgba(255,255,255,.78),
    0 0 0 4px rgba(98,247,255,.48),
    -28px 0 70px rgba(255,56,189,.4),
    28px 0 70px rgba(98,247,255,.42),
    0 42px 90px rgba(0,0,0,.88) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-grid-scene="abyss"][data-pdc-orbit-active="true"] [data-pdc-orbit-selected="true"]::after {
  content: none !important;
  display: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-motion="reduced"],[data-pdc-motion="paused"],[data-pdc-motion-intensity="reduced"]) #pdc-orbital-abyss *,
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-motion="reduced"],[data-pdc-motion="paused"],[data-pdc-motion-intensity="reduced"]) [data-pdc-orbit-card="true"] {
  animation-duration: .001ms !important;
  animation-iteration-count: 1 !important;
  transition-duration: .001ms !important;
}
`;
