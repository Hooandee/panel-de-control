import type { Layout } from "./layout";
import { saveLayout } from "./store";
import { setShellMode } from "../sections/shellMode";

export function updateShowHome(layout: Layout, showHome: boolean): void {
  saveLayout({ ...layout, showHome });
  setShellMode(showHome ? "home" : "tabs");
}

export function resetHomeMode(): void {
  setShellMode("home");
}
