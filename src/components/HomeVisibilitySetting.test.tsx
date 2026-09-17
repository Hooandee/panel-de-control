// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomeVisibilitySetting } from "./HomeVisibilitySetting";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, noFocusRing: _noFocusRing, ...props }: HTMLAttributes<HTMLDivElement> & {
    children?: ReactNode;
    noFocusRing?: boolean;
    onActivate?: () => void;
  }) => (
    <div
      onClick={(event) => {
        onActivate?.();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </div>
  ),
  ToggleField: ({ label, description, checked, onChange }: {
    label: string;
    description: string;
    checked: boolean;
    onChange: (value: boolean) => void;
  }) => (
    <button type="button" aria-label={label} data-description={description} onClick={() => onChange(!checked)}>
      {String(checked)}
    </button>
  ),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "customize.home": "Vista principal",
      "customize.home.desc": "Elige cómo navegar por Panel de Control.",
      "customize.home.dashboard": "Dashboard",
      "customize.home.tabs": "Pestañas",
      "customize.deviceHeader": "Mostrar información del dispositivo",
      "customize.deviceHeader.desc": "Muestra el modelo y el procesador en la parte superior del panel.",
    })[key] ?? key,
  }),
}));

describe("HomeVisibilitySetting", () => {
  afterEach(cleanup);

  it("selects Dashboard or Tabs exactly once", () => {
    const onChange = vi.fn();
    render(
      <HomeVisibilitySetting
        value={true}
        onChange={onChange}
        deviceHeaderValue={true}
        onDeviceHeaderChange={vi.fn()}
      />,
    );

    const dashboard = screen.getByRole("button", { name: "Dashboard" });
    const tabs = screen.getByRole("button", { name: "Pestañas" });
    expect(screen.getByRole("group", { name: "Vista principal" }).getAttribute("data-description")).toBe(
      "Elige cómo navegar por Panel de Control.",
    );
    expect(dashboard.getAttribute("aria-pressed")).toBe("true");
    expect(tabs.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(tabs);

    expect(onChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it("emits the next device information visibility", () => {
    const onDeviceHeaderChange = vi.fn();
    render(
      <HomeVisibilitySetting
        value={true}
        onChange={vi.fn()}
        deviceHeaderValue={true}
        onDeviceHeaderChange={onDeviceHeaderChange}
      />,
    );

    const control = screen.getByRole("button", { name: "Mostrar información del dispositivo" });
    expect(control.dataset.description).toBe("Muestra el modelo y el procesador en la parte superior del panel.");
    fireEvent.click(control);
    expect(onDeviceHeaderChange).toHaveBeenCalledWith(false);
  });
});
