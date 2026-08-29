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
}));

vi.mock("./ContainedSlider", () => ({
  ContainedSlider: ({ value, onChange }: { value: number; onChange: (value: number) => void }) => (
    <input aria-label="slider" type="range" value={value} onChange={(event) => onChange(Number(event.target.value))} />
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

  it("maps a dropdown back to one of CSS Loader's advertised strings", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "dropdown", rawType: "dropdown" }} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Motion intensity"), { target: { value: "Full" } });

    expect(onChange).toHaveBeenCalledWith("Full");
  });

  it("uses slider position only as an index into CSS Loader options", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "slider" }} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("slider"), { target: { value: "2" } });

    expect(onChange).toHaveBeenCalledWith("Full");
  });

  it("keeps an incoherent slider value read-only instead of inventing option zero", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "slider", value: "Future" }} onChange={onChange} />);

    expect(screen.getByText("Future")).toBeTruthy();
    expect(screen.queryByLabelText("slider")).toBeNull();
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

  it("renders an unknown type as read-only instead of crashing", () => {
    const onChange = vi.fn();
    render(<ThemePatchControl patch={{ ...basePatch, type: "unsupported", rawType: "future-type" }} onChange={onChange} />);

    expect(screen.getByText("Motion intensity")).toBeTruthy();
    expect(screen.getByText("future-type")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });
});
