// @vitest-environment happy-dom
import { CSSProperties, HTMLAttributes, ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({
    children,
    onActivate,
    onClick,
    ...props
  }: {
    children?: ReactNode;
    onActivate?: () => void;
  } & HTMLAttributes<HTMLDivElement>) => (
    <div
      {...props}
      data-testid="focusable"
      onClick={(event) => {
        onActivate?.();
        onClick?.(event);
      }}
    >
      {children}
    </div>
  ),
}));

import { QamAction } from "./QamAction";

describe("QamAction", () => {
  afterEach(cleanup);

  it("deduplicates Decky's activate and click callbacks", () => {
    const onPress = vi.fn();
    render(<QamAction onPress={onPress}>Run</QamAction>);

    screen.getByText("Run").click();

    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("exposes selection and expansion state", () => {
    render(
      <QamAction onPress={() => {}} pressed expanded>
        Open
      </QamAction>,
    );

    expect(screen.getByTestId("focusable").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("focusable").getAttribute("aria-expanded")).toBe("true");
  });

  it("renders disabled actions outside the focus tree", () => {
    render(
      <QamAction
        onPress={() => {}}
        disabled
        style={{ width: 28 } as CSSProperties}
      >
        Up
      </QamAction>,
    );

    expect(screen.queryByTestId("focusable")).toBeNull();
    expect(screen.getByText("Up").getAttribute("aria-hidden")).toBe("true");
  });
});
