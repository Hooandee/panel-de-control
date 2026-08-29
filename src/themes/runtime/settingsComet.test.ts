// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { startSettingsComet } from "./settingsComet";

describe("Obsidian settings comet", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("data-pdc-settings-comet");
    document.documentElement.style.removeProperty("--pdc-settings-comet-y");
    document.documentElement.style.removeProperty("--pdc-settings-comet-height");
    document.body.innerHTML = "";
  });

  it("tracks only settings tabs and never creates interactive DOM", () => {
    document.body.innerHTML = `
      <main id="Main"><div class="PageListColumn">
        <button role="tab" id="/settings/display">Display</button>
      </div><button id="outside">Outside</button></main>`;
    const tab = document.querySelector('[role="tab"]') as HTMLElement;
    tab.getBoundingClientRect = () => new DOMRect(12, 80, 220, 40);
    const stop = startSettingsComet(document);

    tab.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect(document.documentElement.dataset.pdcSettingsComet).toBe("active");
    expect(document.documentElement.style.getPropertyValue("--pdc-settings-comet-y")).toBe("100px");
    expect(document.documentElement.style.getPropertyValue("--pdc-settings-comet-height")).toBe("40px");
    expect(document.querySelectorAll("[data-pdc-settings-comet-host]")).toHaveLength(0);

    document.getElementById("outside")?.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect(document.documentElement.hasAttribute("data-pdc-settings-comet")).toBe(false);
    stop();
  });

  it("restores existing root state on disposal", () => {
    const root = document.documentElement;
    root.dataset.pdcSettingsComet = "legacy";
    root.style.setProperty("--pdc-settings-comet-y", "7px");
    root.style.setProperty("--pdc-settings-comet-height", "9px");
    const stop = startSettingsComet(document);

    document.dispatchEvent(new Event("visibilitychange"));
    stop();
    expect(root.dataset.pdcSettingsComet).toBe("legacy");
    expect(root.style.getPropertyValue("--pdc-settings-comet-y")).toBe("7px");
    expect(root.style.getPropertyValue("--pdc-settings-comet-height")).toBe("9px");
  });
});
