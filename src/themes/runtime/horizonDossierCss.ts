export const HORIZON_DOSSIER_CSS = `
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier {
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  position: fixed;
  z-index: 0;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-layer] {
  inset: 0;
  position: absolute;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-layer="void"] {
  background:
    radial-gradient(ellipse at 19% 49%, rgba(68,217,255,.2), transparent 24%),
    radial-gradient(ellipse at 88% 8%, rgba(255,45,174,.13), transparent 30%),
    linear-gradient(118deg, #010207 0 31%, #050914 58%, #020205);
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-layer="horizon"] {
  background:
    linear-gradient(90deg, transparent 0 7%, rgba(98,247,255,.34) 7% 7.15%, transparent 7.15% 91%, rgba(255,56,189,.28) 91% 91.14%, transparent 91.14%),
    linear-gradient(180deg, transparent 0 52%, rgba(98,247,255,.16) 52% 52.2%, transparent 52.2%);
  clip-path: polygon(0 0,100% 0,100% 100%,34% 100%,29% 77%,0 77%);
  opacity: .58;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-layer="frame"] {
  background:
    linear-gradient(135deg, rgba(98,247,255,.24), transparent 13%) top left / 24% 24% no-repeat,
    linear-gradient(315deg, rgba(255,56,189,.18), transparent 14%) bottom right / 28% 30% no-repeat;
  opacity: .66;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-panel-frame="true"] {
  animation: pdc-dossier-frame-in 520ms var(--pdc-obsidian-ease) 70ms both;
  background:
    linear-gradient(135deg,rgba(98,247,255,.32),transparent 22%) border-box,
    linear-gradient(315deg,rgba(255,56,189,.24),transparent 26%) border-box;
  border: 1px solid rgba(152,239,255,.32);
  border-radius: 28px;
  bottom: 4.6vh;
  box-shadow: -18px 0 72px rgba(25,213,255,.08),18px 0 78px rgba(255,45,174,.08),0 30px 90px rgba(0,0,0,.72);
  left: 33.5vw;
  position: absolute;
  right: 2.4vw;
  top: 4.6vh;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-cover="true"] {
  animation: pdc-dossier-cover-in 540ms var(--pdc-obsidian-ease) 80ms both;
  aspect-ratio: .575;
  background-image: var(--pdc-dossier-artwork);
  background-position: center;
  background-size: cover;
  border: 1px solid rgba(255,255,255,.7);
  border-radius: 22px;
  box-shadow:
    0 0 0 3px rgba(98,247,255,.44),
    -28px 0 76px rgba(255,56,189,.28),
    28px 0 76px rgba(98,247,255,.32),
    0 34px 86px rgba(0,0,0,.84);
  left: 18.5vw;
  position: absolute;
  top: 49vh;
  transform: translate3d(-50%,-50%,0) perspective(900px) rotateY(5deg) rotateZ(-1.2deg);
  width: min(23.5vw,252px,calc(64vh * .575));
  z-index: 4;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-cover="true"]::after {
  background:
    linear-gradient(135deg,rgba(255,255,255,.28),transparent 24%),
    linear-gradient(315deg,rgba(98,247,255,.12),transparent 32%);
  border: 1px solid rgba(98,247,255,.52);
  border-radius: inherit;
  content: "";
  inset: 7px;
  position: absolute;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-orbit-node] {
  aspect-ratio: .62;
  background:
    linear-gradient(145deg,rgba(98,247,255,.16),rgba(9,13,25,.88) 46%,rgba(255,56,189,.12));
  border: 1px solid rgba(154,232,244,.2);
  border-radius: 12px;
  box-shadow: 0 16px 38px rgba(0,0,0,.52);
  opacity: .54;
  position: absolute;
  width: 7.2vw;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-orbit-node="0"] {
  animation: pdc-dossier-node-in 460ms var(--pdc-obsidian-ease) 150ms both;
  left: 5.4vw;
  top: 13vh;
  transform: rotate(-8deg);
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-orbit-node="1"] {
  animation: pdc-dossier-node-in 460ms var(--pdc-obsidian-ease) 210ms both;
  left: 25.2vw;
  top: 8vh;
  transform: rotate(7deg) scale(.72);
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #pdc-horizon-dossier [data-pdc-dossier-orbit-node="2"] {
  animation: pdc-dossier-node-in 460ms var(--pdc-obsidian-ease) 270ms both;
  left: 7.6vw;
  top: 75vh;
  transform: rotate(9deg) scale(.8);
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"]:not(#pdc-native-details):not(#pdc-native-details-override) {
  animation: pdc-dossier-panel-in 520ms var(--pdc-obsidian-ease) 70ms both !important;
  background: linear-gradient(180deg,rgba(4,9,17,.98),rgba(1,3,8,.99) 58%,#010207) !important;
  border: 1px solid rgba(171,235,244,.2);
  border-radius: 27px;
  bottom: 4.6vh !important;
  box-shadow: 0 28px 84px rgba(0,0,0,.68) !important;
  height: auto !important;
  isolation: isolate;
  left: 33.5vw !important;
  max-height: none !important;
  overflow: hidden !important;
  position: fixed !important;
  right: 2.4vw !important;
  top: 4.6vh !important;
  width: auto !important;
  z-index: 2;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-hero="true"] {
  animation: pdc-dossier-hero-in 220ms ease-out both !important;
  filter: none !important;
  mask-image: linear-gradient(180deg,#000 0 58%,rgba(0,0,0,.82) 76%,transparent 100%);
  opacity: .72 !important;
  transform-origin: 68% 30%;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-tabs="true"] {
  animation: pdc-dossier-rail-in 340ms var(--pdc-obsidian-ease) 100ms both;
  background: linear-gradient(90deg,rgba(2,7,14,.98),rgba(8,19,31,.95) 62%,rgba(15,5,18,.96)) !important;
  border-block: 1px solid rgba(98,247,255,.26);
  border-radius: 3px !important;
  box-shadow: 0 16px 34px rgba(0,0,0,.38) !important;
  clip-path: polygon(2% 0,98% 0,100% 50%,98% 100%,2% 100%,0 50%);
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-tab="true"] {
  background: transparent !important;
  border-radius: 2px !important;
  color: rgba(202,221,232,.66) !important;
  font-family: "PDC Oxanium","Motiva Sans",sans-serif !important;
  font-weight: 600 !important;
  letter-spacing: .075em;
  text-transform: uppercase;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-tab="true"]:is(.gpfocus,[aria-selected="true"]) {
  background: linear-gradient(90deg,rgba(98,247,255,.18),rgba(98,247,255,.04)) !important;
  box-shadow: inset 0 -2px #62f7ff, inset 0 1px rgba(255,255,255,.12) !important;
  color: white !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"]:not(#pdc-native-details):not(#pdc-native-details-override) [data-pdc-dossier-primary-action="true"] {
  -webkit-backdrop-filter: none !important;
  animation: pdc-dossier-action-in 320ms var(--pdc-obsidian-ease) 60ms both;
  backdrop-filter: none !important;
  background: linear-gradient(108deg,#d9feff 0 4px,#0b6175 4px 68%,#1c1839 100%) !important;
  border: 1px solid rgba(168,249,255,.88) !important;
  border-radius: 3px !important;
  box-shadow: 0 0 0 1px rgba(98,247,255,.18),0 12px 30px rgba(0,0,0,.48) !important;
  clip-path: polygon(0 0,94% 0,100% 50%,94% 100%,0 100%,4% 50%);
  font-family: "PDC Oxanium","Motiva Sans",sans-serif !important;
  letter-spacing: .08em;
  text-transform: uppercase;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"]:not(#pdc-native-details):not(#pdc-native-details-override) [data-pdc-dossier-primary-action="true"].gpfocus {
  background: linear-gradient(108deg,#fff 0 5px,#0b8ca2 5px 72%,#4c1b59 100%) !important;
  box-shadow: 0 0 0 2px rgba(98,247,255,.52),0 0 26px rgba(98,247,255,.3),0 16px 36px rgba(0,0,0,.54) !important;
  transform: translate3d(4px,0,0) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-content="true"] {
  animation: pdc-dossier-content-in 400ms var(--pdc-obsidian-ease) 150ms both;
  background: linear-gradient(180deg,rgba(1,4,10,.94),#010207 46%) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] * {
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"] img {
  filter: none !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"]:not(#pdc-native-details):not(#pdc-native-details-override) [data-pdc-dossier-card="true"] {
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
  background: linear-gradient(112deg,rgba(9,22,34,.96),rgba(10,9,19,.98)) !important;
  border: 1px solid rgba(171,229,242,.15) !important;
  border-left: 3px solid rgba(98,247,255,.68) !important;
  border-radius: 3px !important;
  box-shadow: 0 12px 26px rgba(0,0,0,.28) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"] #Main[data-pdc-horizon-dossier="true"]:not(#pdc-native-details):not(#pdc-native-details-override) [data-pdc-dossier-card="true"].gpfocus {
  border-color: rgba(98,247,255,.75) !important;
  box-shadow: 0 0 0 1px rgba(98,247,255,.34),0 12px 28px rgba(0,0,0,.4) !important;
  transform: translate3d(5px,0,0) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-portal-phase="exit"] #Main[data-pdc-horizon-dossier="true"]:not(#pdc-native-details):not(#pdc-native-details-override) {
  animation: pdc-dossier-panel-out 220ms ease-in both !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-motion="reduced"],[data-pdc-motion="paused"],[data-pdc-motion-intensity="reduced"]) #Main[data-pdc-horizon-dossier="true"],
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-motion="reduced"],[data-pdc-motion="paused"],[data-pdc-motion-intensity="reduced"]) #Main[data-pdc-horizon-dossier="true"] * {
  animation-delay: 0ms !important;
  animation-duration: .001ms !important;
  animation-iteration-count: 1 !important;
  transition-duration: .001ms !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"]:is([data-pdc-motion="reduced"],[data-pdc-motion="paused"],[data-pdc-motion-intensity="reduced"]) #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-hero="true"] {
  animation-delay: 0ms !important;
  animation-duration: .001ms !important;
}
@keyframes pdc-dossier-panel-in {
  from { opacity: 0; transform: translate3d(20vw,0,0) perspective(1100px) rotateY(-9deg) scale(.96); }
  to { opacity: 1; transform: none; }
}
@keyframes pdc-dossier-panel-out {
  from { opacity: 1; transform: none; }
  to { opacity: 0; transform: translate3d(13vw,0,0) perspective(1100px) rotateY(-6deg) scale(.97); }
}
@keyframes pdc-dossier-frame-in {
  from { opacity: 0; transform: translate3d(15vw,0,0) scale(.97); }
  to { opacity: 1; transform: none; }
}
@keyframes pdc-dossier-cover-in {
  from { opacity: 0; transform: translate3d(-35%,-50%,0) perspective(900px) rotateY(16deg) rotateZ(-5deg) scale(.86); }
  to { opacity: 1; transform: translate3d(-50%,-50%,0) perspective(900px) rotateY(5deg) rotateZ(-1.2deg); }
}
@keyframes pdc-dossier-node-in {
  from { opacity: 0; margin-top: 22px; }
}
@keyframes pdc-dossier-hero-in {
  from { opacity: .58; }
  to { opacity: .72; }
}
@keyframes pdc-dossier-rail-in {
  from { opacity: 0; transform: translate3d(0,18px,0) scaleX(.96); }
  to { opacity: 1; transform: none; }
}
@keyframes pdc-dossier-action-in {
  from { opacity: 0; transform: translate3d(-28px,0,0); }
  to { opacity: 1; transform: none; }
}
@keyframes pdc-dossier-content-in {
  from { opacity: 0; transform: translate3d(0,24px,0); }
  to { opacity: 1; transform: none; }
}
`;
