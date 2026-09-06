// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  ToggleField: ({ label, checked, onChange }: { label: ReactNode; checked: boolean; onChange: (value: boolean) => void }) => (
    <button onClick={() => onChange(!checked)}>{label}</button>
  ),
  DropdownItem: ({ label, rgOptions, selectedOption, onChange }: {
    label: ReactNode;
    rgOptions: Array<{ label: string; data: string }>;
    selectedOption: string;
    onChange: (value: { data: string }) => void;
  }) => (
    <label>{label}<select aria-label={String(label)} value={selectedOption} onChange={(event) => onChange({ data: event.target.value })}>
      {rgOptions.map((option) => <option key={option.data} value={option.data}>{option.label}</option>)}
    </select></label>
  ),
  SliderField: ({ value, disabled, label, onChange }: { value: number; disabled?: boolean; label?: ReactNode; onChange: (value: number) => void }) => (
    <label>{label}<input type="range" value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} /></label>
  ),
}));

import { ThemePatchControl } from "./ThemePatchControl";

const basePatch = {
  name: "Motion intensity",
  defaultValue: "Balanced",
  value: "Balanced",
  options: ["Reduced", "Balanced", "Full"],
  rawType: "slider",
} as const;

describe("ThemePatchControl", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("maps a checkbox back to CSS Loader's exact Yes/No values", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, name: "Animated grid", type: "checkbox", value: "Yes", options: ["No", "Yes"], rawType: "checkbox" }} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Animated grid" }));

    expect(onChange).toHaveBeenCalledWith("No");
  });

  it("gives editable controls one shared Panel surface", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, name: "Animated grid", type: "checkbox", value: "Yes", options: ["No", "Yes"], rawType: "checkbox" }} onChange={onChange} />);

    const surface = screen.getByTestId("theme-patch-control");
    expect(surface.getAttribute("data-pdc-theme-patch-control")).toBe("true");
    expect(surface.style.padding).toBe("10px 11px");
    expect(surface.style.borderRadius).toBe("14px");
    expect(surface.style.boxSizing).toBe("border-box");
  });

  it("maps a dropdown back to one of CSS Loader's advertised strings", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "dropdown", rawType: "dropdown" }} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Motion intensity"), { target: { value: "Full" } });

    expect(onChange).toHaveBeenCalledWith("Full");
  });

  it("uses slider position only as an index into CSS Loader options", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "slider" }} onChange={onChange} />);

    const slider = screen.getByRole("slider", { name: /Motion intensity/ });
    fireEvent.change(slider, { target: { value: "2" } });

    expect(onChange).toHaveBeenCalledWith("Full");
    expect(screen.getByTestId("theme-patch-control").getAttribute("data-pdc-theme-slider")).toBe("true");
  });

  it("makes a slider visibly and functionally disabled during any theme operation", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "slider" }} disabled onChange={onChange} />);

    const slider = screen.getByRole("slider", { name: /Motion intensity/ }) as HTMLInputElement;
    expect(slider.disabled).toBe(true);
    fireEvent.change(slider, { target: { value: "2" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps an incoherent slider value read-only instead of inventing option zero", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "slider", value: "Future" }} onChange={onChange} />);

    expect(screen.getByText("Future")).toBeTruthy();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it.each(["checkbox", "dropdown"] as const)("keeps an incoherent %s value read-only", (type) => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type, value: "Future", rawType: type }} onChange={onChange} />);

    expect(screen.getByText("Future")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps a checkbox without the exact Yes/No contract read-only", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "checkbox", value: "Yes", options: ["Yes"], rawType: "checkbox" }} onChange={onChange} />);

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Yes")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps a slider with no alternative value read-only", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "slider", value: "Only", options: ["Only"] }} onChange={onChange} />);

    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.getByText("Only")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("renders an unknown type as read-only instead of crashing", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "unsupported", rawType: "future-type" }} onChange={onChange} />);

    expect(screen.getByText("Motion intensity")).toBeTruthy();
    expect(screen.getByText("future-type")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });
});
