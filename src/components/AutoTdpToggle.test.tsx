// @vitest-environment happy-dom
import { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ToggleField: ({ label }: { label: ReactNode }) => <button>{label}</button>,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => `copy:${key}` }),
}));

import { AutoTdpToggle } from "./AutoTdpToggle";

describe("AutoTdpToggle experimental label", () => {
  afterEach(cleanup);

  it("places the shared experimental pill above the title", () => {
    render(<AutoTdpToggle checked={false} onChange={vi.fn()} />);

    const badge = screen.getByText("copy:tdp.auto.experimental");
    const label = badge.parentElement!;

    expect(badge.getAttribute("data-pdc-experimental-badge")).toBe("true");
    expect(label.style.flexDirection).toBe("column");
    expect(label.style.alignItems).toBe("flex-start");
    expect(label.firstChild).toBe(badge);
  });
});
