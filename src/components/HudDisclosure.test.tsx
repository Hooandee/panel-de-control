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

  it("keeps a narrow title on one line and truncates the summary first", () => {
    render(
      <HudDisclosure
        id="hud-font-refine"
        icon={<span>T</span>}
        title="Refine by type"
        summary="Main · details · text"
      >
        <span>Controls</span>
      </HudDisclosure>,
    );

    const title = screen.getByText("Refine by type");
    const summary = screen.getByText("Main · details · text");
    expect(title.style.whiteSpace).toBe("nowrap");
    expect(title.style.overflow).toBe("hidden");
    expect(title.style.textOverflow).toBe("ellipsis");
    expect(summary.style.flexGrow).toBe("1");
    expect(summary.style.flexShrink).toBe("1");
    expect(summary.style.flexBasis).toBe("0px");
    expect(summary.style.maxWidth).toBe("46%");
    expect(summary.style.textAlign).toBe("right");
  });
});
