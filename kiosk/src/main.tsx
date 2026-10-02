import "./installSteamGlobals";
import { createRoot } from "react-dom/client";

import "../../src/system/useAccent";
import { I18nProvider } from "../../src/i18n";
import { becomePrefsFollower, followBackendPrefs } from "../../src/system/pdcStorage";
import { registerSystemBlocks } from "../../src/sections/systemBlocks";
import { registerFanBlocks } from "../../src/sections/fanBlocks";
import { registerDisplayBlocks } from "../../src/sections/displayBlocks";
import { registerMandosBlocks } from "../../src/sections/mandosBlocks";
import { registerPowerBlocks } from "../../src/sections/powerBlocks";
import { KioskApp } from "./KioskApp";
import { KIOSK_CSS, KIOSK_LOGICAL_WIDTH } from "./styles";

registerSystemBlocks();
registerFanBlocks();
registerDisplayBlocks();
registerMandosBlocks();
registerPowerBlocks();

function fitToScreen(): void {
  document.documentElement.style.setProperty("zoom", String(window.innerWidth / KIOSK_LOGICAL_WIDTH));
}

const style = document.createElement("style");
style.textContent = KIOSK_CSS;
document.head.appendChild(style);
fitToScreen();
window.addEventListener("resize", fitToScreen);

const PREFS_SYNC_MS = 5000;

becomePrefsFollower();

void followBackendPrefs().finally(() => {
  window.setInterval(() => void followBackendPrefs(), PREFS_SYNC_MS);
  createRoot(document.getElementById("kiosk")!).render(
    <I18nProvider>
      <KioskApp />
    </I18nProvider>,
  );
});
