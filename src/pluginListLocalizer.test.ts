// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./i18n", () => ({
  translate: () => "Control Panel",
}));

import { setQamDocument } from "./qamDocument";
import { startPluginListLocalizer } from "./pluginListLocalizer";

describe("plugin list localizer", () => {
  let stop: (() => void) | undefined;

  afterEach(() => {
    stop?.();
    stop = undefined;
    document.body.replaceChildren();
  });

  it("localizes a newly rendered plugin row before a timer elapses", async () => {
    setQamDocument(document);
    stop = startPluginListLocalizer();

    const row = document.createElement("div");
    row.textContent = "Panel de Control";
    document.body.append(row);
    await Promise.resolve();

    expect(row.textContent).toBe("Control Panel");
  });
});
