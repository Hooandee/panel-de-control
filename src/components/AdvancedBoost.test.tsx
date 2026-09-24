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
      "tdp.deckPpt.hint": "La Steam Deck utiliza estos límites de impulso cuando la carga lo necesita.",
      "tdp.boost.mode.auto": "Auto",
      "tdp.boost.mode.custom": "Personalizado",
    } as Record<string, string>)[key] ?? key,
  }),
}));

import { AdvancedBoost } from "./AdvancedBoost";

describe("AdvancedBoost narrow QAM layout", () => {
  afterEach(cleanup);

  it("spaces the Deck hint, mode pills, and content while marqueeing long mode labels", () => {
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
    const hint = screen.getByText("La Steam Deck utiliza estos límites de impulso cuando la carga lo necesita.");
    expect(hint.style.marginTop).toBe("8px");

    let modeGroup: HTMLElement | null = null;
    for (const label of ["Desactivado", "Auto", "Personalizado"]) {
      const matches = screen.getAllByText(label);
      const option = matches[matches.length - 1] as HTMLElement;
      expect(option.style.whiteSpace).toBe("nowrap");
      expect(option.parentElement?.style.overflow).toBe("hidden");
      expect(option.parentElement?.style.textAlign).toBe("center");
      const pill = option.closest("button");
      modeGroup ??= pill?.parentElement ?? null;
    }
    expect(modeGroup?.style.gap).toBe("8px");

    const rails = screen.getByText(/SlowPPT 22 W/).parentElement as HTMLElement;
    expect(rails.style.marginTop).toBe("12px");
  });
});

describe("AdvancedBoost Steam Deck BIOS notice", () => {
  afterEach(cleanup);

  const ppt = {
    supported: true,
    source: "sysfs" as const,
    visual_max: 30,
    requested: { slow: 15, fast: 20 },
    applied: { slow: 15, fast: 20 },
    slow: { min: 3, max: 29 },
    fast: { min: 3, max: 30 },
  };

  const renderBoost = (levels: { pl1: number; pl2: number; pl3: number }, biosNoticeAbove: number | null) => {
    render(
      <AdvancedBoost
        levels={levels}
        mode="custom"
        bounds={{ pl2: { min: 3, max: 29 }, pl3: { min: 3, max: 30 } }}
        ppt={ppt}
        biosNoticeAbove={biosNoticeAbove}
        onSetMode={vi.fn()}
        onSetLevels={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Impulso de potencia").closest("button")!);
  };

  it("warns that a stock Deck needs a modded BIOS once a rail passes its ceiling", () => {
    renderBoost({ pl1: 15, pl2: 15, pl3: 20 }, 15);
    expect(screen.getByText("tdp.deckPpt.biosRequired")).toBeTruthy();
  });

  it("stays silent within the ceiling", () => {
    renderBoost({ pl1: 12, pl2: 15, pl3: 15 }, 15);
    expect(screen.queryByText("tdp.deckPpt.biosRequired")).toBeNull();
  });

  it("stays silent on an overclocked Deck", () => {
    renderBoost({ pl1: 25, pl2: 29, pl3: 30 }, null);
    expect(screen.queryByText("tdp.deckPpt.biosRequired")).toBeNull();
  });
});
