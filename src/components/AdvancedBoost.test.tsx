// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, style }: any) => (
    <button type="button" onClick={onClick} style={style}>{children}</button>
  ),
  SliderField: () => <div />,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "tdp.deckPpt.title": "Impulso de potencia",
      "tdp.deckPpt.experimental": "Experimental",
      "tdp.deckPpt.off": "Desactivado",
      "tdp.boost.mode.auto": "Auto",
      "tdp.boost.mode.custom": "Personalizado",
    } as Record<string, string>)[key] ?? key,
  }),
}));

import { AdvancedBoost } from "./AdvancedBoost";

describe("AdvancedBoost narrow QAM layout", () => {
  afterEach(cleanup);

  it("keeps the title separate from both badges and allows mode labels to wrap", () => {
    render(
      <div style={{ width: 260 }}>
        <AdvancedBoost
          levels={{ pl1: 12, pl2: 22, pl3: 28 }}
          mode="custom"
          bounds={{ pl2: { min: 3, max: 29 }, pl3: { min: 3, max: 30 } }}
          ppt={{
            supported: true,
            source: "sysfs",
            visual_max: 30,
            requested: { slow: 22, fast: 28 },
            applied: { slow: 22, fast: 28 },
            slow: { min: 3, max: 29 },
            fast: { min: 3, max: 30 },
          }}
          onSetMode={vi.fn()}
          onSetLevels={vi.fn()}
        />
      </div>,
    );

    const title = screen.getByText("Impulso de potencia");
    const experimental = screen.getByText("Experimental");
    const currentMode = screen.getByText("Personalizado");
    expect(title.parentElement).not.toBe(experimental.parentElement);
    expect(title.parentElement).not.toBe(currentMode.parentElement);

    fireEvent.click(title.closest("button")!);
    for (const label of ["Desactivado", "Auto", "Personalizado"]) {
      const matches = screen.getAllByText(label);
      const option = matches[matches.length - 1] as HTMLElement;
      expect(option.style.whiteSpace).toBe("normal");
      expect(option.style.overflowWrap).toBe("anywhere");
    }
  });
});
