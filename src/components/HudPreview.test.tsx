// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => `copy:${key}` }),
}));

import { DEFAULT_MODEL, HudModel, previewWouldClip } from "../mangohud/model";
import { HudPreview } from "./HudPreview";

describe("HudPreview typography", () => {
  afterEach(cleanup);

  it("uses the secondary size for units and the text size for free text", () => {
    const model = {
      ...DEFAULT_MODEL,
      fontSizeSecondary: 14,
      fontSizeText: 30,
      items: [
        { kind: "metric", id: "gpu" },
        { kind: "text", id: "note", text: "Steam Deck" },
      ],
    } as HudModel;

    render(<HudPreview model={model} />);

    const unit = document.querySelector("[data-hud-value-unit]") as HTMLElement;
    const freeText = document.querySelector("[data-hud-free-text]") as HTMLElement;
    expect(unit.textContent).toBe("%");
    expect(unit.style.fontSize).toBe("7px");
    expect(freeText.textContent).toBe("Steam Deck");
    expect(freeText.style.fontSize).toBe("15px");
  });

  it("clips an overflowing overlay and warns outside the simulated frame", () => {
    const model = {
      ...DEFAULT_MODEL,
      fontSize: 40,
      items: Array.from({ length: 14 }, (_, index) => ({
        kind: "text" as const,
        id: `line-${index}`,
        text: `Line ${index}`,
      })),
    } as HudModel;

    render(<HudPreview model={model} />);

    const overlay = screen.getByTestId("hud-preview-overlay");
    const frame = screen.getByTestId("hud-preview-frame");
    const warning = screen.getByTestId("hud-preview-clipping-warning");
    expect(previewWouldClip(model)).toBe(true);
    expect(frame.contains(warning)).toBe(false);
    expect(overlay.style.overflow).toBe("hidden");
    expect(overlay.style.overflowY).toBe("");
  });
});
