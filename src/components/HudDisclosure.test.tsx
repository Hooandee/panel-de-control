// @vitest-environment happy-dom
import { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../system/collapseState", () => ({
  isCollapsed: () => true,
  setCollapsed: vi.fn(),
}));

vi.mock("./QamAction", () => ({
  QamAction: ({
    children,
    expanded,
    onPress,
  }: {
    children: ReactNode;
    expanded?: boolean;
    onPress: () => void;
  }) => (
    <button aria-expanded={expanded} onClick={onPress}>
      {children}
    </button>
  ),
}));

import { HudDisclosure } from "./HudDisclosure";

describe("HudDisclosure", () => {
  afterEach(cleanup);

  it("is a card-only disclosure with explicit expansion state", () => {
    render(
      <HudDisclosure
        id="hud-test"
        icon={<span>i</span>}
        title="Style"
        summary="Closed"
      >
        <span>Controls</span>
      </HudDisclosure>,
    );

    expect(screen.getByText("Closed")).toBeTruthy();
    const trigger = screen.getByRole("button");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(trigger);

    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Controls")).toBeTruthy();
    expect(document.querySelector("[data-panel-section-row]")).toBeNull();
  });
});
