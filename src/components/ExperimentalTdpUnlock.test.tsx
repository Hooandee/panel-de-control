// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ modal: null as ReactNode }));

vi.mock("@decky/ui", () => ({
  ToggleField: ({ label, description, checked, onChange }: any) => (
    <button type="button" onClick={() => onChange(!checked)}>{label}{description}</button>
  ),
  showModal: (node: ReactNode) => { mocks.modal = node; },
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("./ConfirmDialog", () => ({
  ConfirmDialog: ({ onConfirm }: { onConfirm: () => void }) => (
    <button type="button" onClick={onConfirm}>confirm</button>
  ),
}));

import { ExperimentalTdpUnlock } from "./ExperimentalTdpUnlock";

describe("ExperimentalTdpUnlock", () => {
  afterEach(() => {
    cleanup();
    mocks.modal = null;
  });

  it("requires confirmation before enabling the unsupported ceiling", () => {
    const onToggle = vi.fn();
    render(<ExperimentalTdpUnlock enabled={false} maxWatts={55} safeMaxWatts={35} onToggle={onToggle} />);

    fireEvent.click(screen.getByRole("button"));
    expect(onToggle).not.toHaveBeenCalled();

    render(<>{mocks.modal}</>);
    fireEvent.click(screen.getByText("confirm"));
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it("disables immediately without another confirmation", () => {
    const onToggle = vi.fn();
    render(<ExperimentalTdpUnlock enabled maxWatts={55} safeMaxWatts={35} onToggle={onToggle} />);

    fireEvent.click(screen.getByRole("button"));

    expect(onToggle).toHaveBeenCalledWith(false);
    expect(mocks.modal).toBeNull();
  });

  it("warns when the safe ceiling could not be confirmed", () => {
    render(
      <ExperimentalTdpUnlock
        enabled
        failed
        maxWatts={55}
        safeMaxWatts={35}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByText(/settings.experimentalTdp.applyFailed/)).toBeTruthy();
  });
});
