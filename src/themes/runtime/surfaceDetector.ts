import type { ThemeRuntimeSurface } from "../types";

export function hasSteamSurfaceSentinel(
  doc: Document,
  surface: ThemeRuntimeSurface,
): boolean {
  if (surface === "game-details") {
    return Boolean(doc.querySelector('[role="tab"][aria-controls$="GameInfo_Content"]'));
  }
  if (surface === "settings") {
    return Boolean(doc.querySelector('.PageListColumn [id*="/settings/"][role="tab"]'));
  }
  if (surface === "library-grid") {
    return Boolean(
      doc.querySelector('[role="tab"][id$="AllGames"]')
      && doc.querySelector('[role="tab"][id$="Soundtracks"]'),
    );
  }
  return Boolean(doc.querySelector('[role="listitem"][data-id="GoToLibrary"]'));
}

export function detectSteamSurface(
  doc: Document,
  previousSurface: ThemeRuntimeSurface | null = null,
): ThemeRuntimeSurface | null {
  const detailsPresent = hasSteamSurfaceSentinel(doc, "game-details");
  const libraryGridPresent = hasSteamSurfaceSentinel(doc, "library-grid");
  const libraryPresent = hasSteamSurfaceSentinel(doc, "library");

  if (previousSurface === "game-details") {
    if (libraryGridPresent) return "library-grid";
    if (libraryPresent) return "library";
  }
  if (detailsPresent) return "game-details";
  if (doc.querySelector('.PageListColumn [id*="/settings/"][role="tab"]')) return "settings";
  if (libraryGridPresent) return "library-grid";
  if (libraryPresent) return "library";

  const classFallbacks: readonly [ThemeRuntimeSurface, string][] = [
    ["game-details", '[class*="appdetails_"]'],
    ["settings", '[class*="settings_"]'],
    ["library-grid", '[class*="allcollections_"]'],
    ["library", '[class*="libraryhome_"]'],
  ];
  for (const [surface, selector] of classFallbacks) {
    if (doc.querySelector(selector)) return surface;
  }

  const route = `${doc.defaultView?.location.pathname ?? ""}${doc.defaultView?.location.hash ?? ""}`.toLocaleLowerCase();
  if (/\/library\/home|\/library$/.test(route)) return "library";
  if (/\/library\/collections|\/collections/.test(route)) return "library-grid";
  if (/\/library\/app\//.test(route)) return "game-details";
  if (/\/settings/.test(route)) return "settings";
  return null;
}
