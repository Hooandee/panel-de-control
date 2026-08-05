// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => `copy:${key}` }),
}));

import { DEFAULT_MODEL, HudModel, previewWouldClip } from "../mangohud/model";
import { HudPreview } from "./HudPreview";

const renderPreview = (patch: Partial<HudModel>) => {
  const model = { ...DEFAULT_MODEL, ...patch } as HudModel;
  return { model, ...render(<HudPreview model={model} />) };
};

describe("HudPreview typography", () => {
  afterEach(cleanup);

  it("uses the secondary font for PdC and added text", () => {
    renderPreview({
      fontSizeSecondary: 14,
      items: [
        { kind: "metric", id: "gpu" },
        { kind: "text", id: "note", text: "Steam Deck" },
      ],
    });

    const unit = document.querySelector("[data-hud-value-unit]") as HTMLElement;
    const freeText = document.querySelector("[data-hud-free-text]") as HTMLElement;
    expect(unit.textContent).toBe("%");
    expect(unit.style.fontSize).toBe("6.6px");
    expect(freeText.textContent).toBe("Steam Deck");
    expect(freeText.style.fontSize).toBe("7px");
  });

  it("does not let font_size_text change custom text", () => {
    renderPreview({
      fontSizeText: 30,
      items: [{ kind: "text", id: "note", text: "Steam Deck" }],
    });

    const freeText = document.querySelector("[data-hud-free-text]") as HTMLElement;
    expect(freeText.style.fontSize).toBe("6.5px");
  });

  it("only applies no_small_font to units and abbreviations", () => {
    renderPreview({
      noSmallFont: true,
      fontSizeSecondary: 14,
      items: [
        { kind: "metric", id: "gpu" },
        { kind: "text", id: "note", text: "Steam Deck" },
      ],
    });

    const unit = document.querySelector("[data-hud-value-unit]") as HTMLElement;
    const freeText = document.querySelector("[data-hud-free-text]") as HTMLElement;
    expect(unit.style.fontSize).toBe("12px");
    expect(freeText.style.fontSize).toBe("7px");
  });

  it("shows the full configured size instead of flattening the slider range", () => {
    renderPreview({
      fontSize: 64,
      fontScale: 2,
      items: [{ kind: "metric", id: "fps" }],
    });

    const overlay = screen.getByTestId("hud-preview-overlay");
    expect(overlay.style.fontSize).toBe("64px");
  });

  it("clips an overflowing overlay and warns outside the simulated frame", () => {
    const { model } = renderPreview({
      fontSize: 40,
      fontSizeSecondary: 40,
      items: Array.from({ length: 14 }, (_, index) => ({
        kind: "text" as const,
        id: `line-${index}`,
        text: `Line ${index}`,
      })),
    });

    const overlay = screen.getByTestId("hud-preview-overlay");
    const frame = screen.getByTestId("hud-preview-frame");
    const warning = screen.getByTestId("hud-preview-clipping-warning");
    expect(previewWouldClip(model)).toBe(true);
    expect(frame.contains(warning)).toBe(false);
    expect(overlay.style.overflow).toBe("hidden");
    expect(overlay.style.overflowY).toBe("");
  });
});
