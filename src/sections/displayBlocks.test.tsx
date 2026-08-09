// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, style }: any) => (
    <div role="button" onClick={onClick} style={style}>{children}</div>
  ),
  PanelSectionRow: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "display.look": "Resa",
      "display.look.comodo": "Riposante",
      "display.look.vivo": "Vivace",
      "display.saturation": "Saturazione",
      "display.advanced": "Avanzate",
      "display.custom": "Personalizzata",
      "display.native": "Nativa",
    } as Record<string, string>)[key] ?? key,
  }),
}));

vi.mock("../display/pantallaContext", () => ({
  usePantalla: () => ({
    color: {
      state: {
        supported: true,
        oled_look: false,
        presets: ["comodo", "vivo"],
        active_preset: "comodo",
        saturation: 100,
        temperature: 0,
        contrast: 0,
        gamma: 0,
        hue: 0,
        black: 0,
        gain_r: 100,
        gain_g: 100,
        gain_b: 100,
        vibrance: 0,
      },
      onPreset: vi.fn(),
      onSaturation: vi.fn(),
      onCalibration: vi.fn(),
      onReset: vi.fn(),
    },
    hdr: { state: null },
    night: { state: null },
  }),
}));

vi.mock("../system/pdcStorage", () => ({
  readString: () => null,
  writeString: vi.fn(),
  removeString: vi.fn(),
  onPrefsHealed: vi.fn(() => () => {}),
}));

vi.mock("../components/ContainedSlider", () => ({ ContainedSlider: () => null }));
vi.mock("../components/Collapsible", () => ({ Collapsible: () => null }));
vi.mock("../components/OledLookCard", () => ({ OledLookCard: () => null }));
vi.mock("../components/AdvancedColor", () => ({ AdvancedColor: () => null }));
vi.mock("../components/NightModeCard", () => ({ NightModeCard: () => null }));
vi.mock("../components/HdrPanel", () => ({ HdrPanel: () => null }));

import { getBlockDef } from "../customize/blocks";
import { registerDisplayBlocks } from "./displayBlocks";

describe("display preset labels", () => {
  afterEach(cleanup);

  it("renders long labels in centered marquee viewports", () => {
    registerDisplayBlocks();
    const ColorBlock = getBlockDef("color")!.Component;
    render(<ColorBlock />);

    for (const label of ["Riposante", "Vivace"]) {
      const text = screen.getByText(label);
      expect(text.tagName).toBe("SPAN");
      expect(text.style.whiteSpace).toBe("nowrap");
      expect(text.parentElement?.style.overflow).toBe("hidden");
      expect(text.parentElement?.style.textAlign).toBe("center");
    }
  });
});
