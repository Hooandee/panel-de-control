import { Navigation } from "@decky/ui";

import { restartLoader } from "../api";

export function reloadDeckyAfterClosingMenus(): void {
  Navigation.CloseSideMenus();
  window.setTimeout(() => { void restartLoader(); }, 500);
}
