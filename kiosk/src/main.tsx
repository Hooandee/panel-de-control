import "./installSteamGlobals";
import { createRoot } from "react-dom/client";

import { I18nProvider } from "../../src/i18n";
import { becomePrefsFollower, followBackendPrefs } from "../../src/system/pdcStorage";
import { KioskApp } from "./KioskApp";
import { followRunningGame } from "./runningGame";
import { KIOSK_CSS, KIOSK_LOGICAL_WIDTH } from "./styles";

function fitToScreen(): void {
  document.documentElement.style.setProperty("zoom", String(window.innerWidth / KIOSK_LOGICAL_WIDTH));
}

const style = document.createElement("style");
style.textContent = KIOSK_CSS;
document.head.appendChild(style);
fitToScreen();
window.addEventListener("resize", fitToScreen);

const PREFS_SYNC_MS = 10_000;

becomePrefsFollower();

followRunningGame();

void followBackendPrefs().finally(() => {
  window.setInterval(() => void followBackendPrefs(), PREFS_SYNC_MS);
  createRoot(document.getElementById("kiosk")!).render(
    <I18nProvider>
      <KioskApp />
    </I18nProvider>,
  );
});
