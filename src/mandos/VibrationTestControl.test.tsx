// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, onClick, disabled, ...props }: any) => (
    <button disabled={disabled} onClick={onClick} {...props}>{children}</button>
  ),
  Dropdown: ({ rgOptions, selectedOption, onChange, disabled }: any) => (
    <select
      aria-label="channel"
      disabled={disabled}
      value={selectedOption}
      onChange={(event) => onChange({ data: event.target.value })}
    >
      {rgOptions.map((option: any) => (
        <option key={option.data} value={option.data}>{option.label}</option>
      ))}
    </select>
  ),
}));

import { VibrationTestControl } from "./VibrationTestControl";

afterEach(cleanup);

const props = {
  disabled: false,
  selectLabel: "Motor",
  buttonLabel: "Probar",
  channelLabel: (channel: string) => channel,
};

describe("VibrationTestControl", () => {
  it("renders nothing without a test channel", () => {
    const view = render(
      <VibrationTestControl {...props} channels={[]} onTest={vi.fn()} />,
    );
    expect(view.container.innerHTML).toBe("");
  });

  it("uses the only channel without showing a selector", () => {
    const onTest = vi.fn();
    render(
      <VibrationTestControl
        {...props}
        channels={["strong"]}
        onTest={onTest}
      />,
    );

    expect(screen.queryByRole("combobox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Probar.*strong/ }));
    expect(onTest).toHaveBeenCalledWith("strong", 50);
  });

  it("renders each available motor as an explicit test action", () => {
    const onTest = vi.fn();
    render(
      <VibrationTestControl
        {...props}
        channels={["strong", "weak", "both"]}
        onTest={onTest}
      />,
    );

    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(onTest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Probar.*weak/ }));
    expect(onTest).toHaveBeenCalledWith("weak", 50);
  });

  it("keeps distinct actions when a combined motor is unavailable", () => {
    const onTest = vi.fn();
    render(
      <VibrationTestControl
        {...props}
        channels={["left", "right"]}
        onTest={onTest}
      />,
    );

    expect(screen.getAllByRole("button")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /Probar.*right/ }));
    expect(onTest).toHaveBeenCalledWith("right", 50);
  });

  it("offers one explicit action per Xbox Ally X motor without a selector", () => {
    const onTest = vi.fn();
    render(
      <VibrationTestControl
        {...props}
        channels={["trigger_left", "trigger_right", "strong", "weak", "all"]}
        onTest={onTest}
      />,
    );

    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", {
      name: /Probar.*trigger_right/,
    }));
    expect(onTest).toHaveBeenCalledWith("trigger_right", 50);
  });

  it("uses one compact action label and a position icon for every motor", () => {
    render(
      <VibrationTestControl
        {...props}
        channels={["trigger_left", "trigger_right", "strong", "weak", "all"]}
        onTest={vi.fn()}
      />,
    );

    expect(screen.queryByText("Probar")).toBeNull();
    for (const channel of ["trigger_left", "trigger_right", "strong", "weak", "all"]) {
      const button = screen.getByTestId(`vibration-test-${channel}`);
      expect(button.style.whiteSpace).toBe("nowrap");
      expect(button.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("disables a zero-strength motor and tests another at its configured strength", () => {
    const onTest = vi.fn();
    render(
      <VibrationTestControl
        {...props}
        channels={["trigger_left", "trigger_right"]}
        channelStrength={(channel) => channel === "trigger_right" ? 0 : 35}
        onTest={onTest}
      />,
    );

    const right = screen.getByTestId("vibration-test-trigger_right");
    expect(right.hasAttribute("disabled")).toBe(true);
    expect(right.textContent).toContain("0%");
    fireEvent.click(right);
    expect(onTest).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("vibration-test-trigger_left"));
    expect(onTest).toHaveBeenCalledWith("trigger_left", 35);
  });

  it("explains that motor tests are manual and separate from game routing", () => {
    render(
      <VibrationTestControl
        {...props}
        channels={["trigger_left"]}
        description="La prueba manual funciona aunque el motor no se use en juegos."
        onTest={vi.fn()}
      />,
    );

    expect(screen.getByText(
      "La prueba manual funciona aunque el motor no se use en juegos.",
    )).toBeTruthy();
  });
});
