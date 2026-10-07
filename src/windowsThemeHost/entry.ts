import { createWindowsThemeHost, WINDOWS_THEME_HOST_VERSION, type WindowsThemeHost } from "./host";

const HOST_KEY = "__pdcWindowsThemeHost";

const scope = globalThis as typeof globalThis & { [HOST_KEY]?: WindowsThemeHost };
const existing = scope[HOST_KEY];
if (existing?.hostVersion !== WINDOWS_THEME_HOST_VERSION) {
  existing?.dispose();
  scope[HOST_KEY] = createWindowsThemeHost(scope);
}
