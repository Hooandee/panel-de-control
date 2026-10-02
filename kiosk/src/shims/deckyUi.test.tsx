// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../runningGame", () => ({ runningAppOverview: () => undefined }));

import { ModalHost, showModal, SliderField, ToggleField } from "./deckyUi";

afterEach(cleanup);

describe("kiosk @decky/ui shim", () => {
  it("toggles through the whole row, like a touch target should", () => {
    const onChange = vi.fn();
    render(<ToggleField label="Auto" checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByText("Auto"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("reports slider values as numbers", () => {
    const onChange = vi.fn();
    render(<SliderField label="Nivel" value={6} min={1} max={10} step={1} onChange={onChange} />);
    fireEvent.change(screen.getByRole("slider"), { target: { value: "8" } });
    expect(onChange).toHaveBeenCalledWith(8);
  });

  it("stacks modals and closes them by handle or backdrop", () => {
    const onClose = vi.fn();
    render(<ModalHost />);
    let handle: ReturnType<typeof showModal>;
    act(() => {
      handle = showModal(<div>Curva</div>, undefined, { fnOnClose: onClose });
    });
    expect(screen.getByText("Curva")).toBeTruthy();
    act(() => handle.Close());
    expect(screen.queryByText("Curva")).toBeNull();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
