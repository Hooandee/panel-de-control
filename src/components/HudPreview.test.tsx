// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_MODEL, HudModel } from "../mangohud/model";
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
});
