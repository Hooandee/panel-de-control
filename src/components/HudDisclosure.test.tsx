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

const renderDisclosure = (title = "Style", summary = "Closed") => render(
  <HudDisclosure id="hud-test" icon={<span>i</span>} title={title} summary={summary}>
    <span>Controls</span>
  </HudDisclosure>,
);

describe("HudDisclosure", () => {
  afterEach(cleanup);

  it("is a card-only disclosure with explicit expansion state", () => {
    renderDisclosure();

    expect(screen.getByText("Closed")).toBeTruthy();
    const trigger = screen.getByRole("button");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(trigger);

    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Controls")).toBeTruthy();
    expect(document.querySelector("[data-panel-section-row]")).toBeNull();
  });

  it("keeps a narrow title on one line and truncates the summary first", () => {
    renderDisclosure("Refine by type", "Main · details · text");

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
