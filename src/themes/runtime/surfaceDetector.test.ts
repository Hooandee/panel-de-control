// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { detectSteamSurface } from "./surfaceDetector";

describe("detectSteamSurface", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/");
  });

  it("detects stable Steam surface families without requiring exact hashed classes", () => {
    document.body.innerHTML = '<div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>';
    expect(detectSteamSurface(document)).toBe("library-grid");

    document.body.innerHTML = '<div role="tab" aria-controls="Tabs_GameInfo_Content"></div>';
    expect(detectSteamSurface(document)).toBe("game-details");

    document.body.innerHTML = '<div class="PageListColumn"><div role="tab" id="/settings/display"></div></div>';
    expect(detectSteamSurface(document)).toBe("settings");

    document.body.innerHTML = '<div role="listitem" data-id="GoToLibrary"></div>';
    expect(detectSteamSurface(document)).toBe("library");
  });

  it("uses the Steam route only as a conservative fallback", () => {
    window.history.replaceState({}, "", "/library/home");
    expect(detectSteamSurface(document)).toBe("library");
    window.history.replaceState({}, "", "/unrelated");
    expect(detectSteamSurface(document)).toBeNull();
  });

  it("resolves Steam's overlapping route trees in the direction of travel", () => {
    document.body.innerHTML = `
      <div role="tab" aria-controls="Tabs_GameInfo_Content"></div>
      <div role="listitem" data-id="GoToLibrary"></div>`;

    expect(detectSteamSurface(document)).toBe("game-details");
    expect(detectSteamSurface(document, "game-details")).toBe("library");
    expect(detectSteamSurface(document, "library")).toBe("game-details");

    document.body.innerHTML = `
      <div role="tab" aria-controls="Tabs_GameInfo_Content"></div>
      <div role="tab" id="Library_AllGames"></div>
      <div role="tab" id="Library_Soundtracks"></div>`;
    expect(detectSteamSurface(document, "game-details")).toBe("library-grid");
  });
});
