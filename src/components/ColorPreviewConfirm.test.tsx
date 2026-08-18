// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, onActivate: _onActivate, style, ...props }: any) => (
    <button onClick={onClick} style={style} {...props}>{children}</button>
  ),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number>) => ({
      "display.confirm.title": "Cambios sin guardar",
      "display.confirm.desc": `Se desharán en ${values?.s}s`,
      "display.confirm.save": "Guardar cambios",
      "display.confirm.discard": "Deshacer",
      "display.confirm.saving": "Guardando…",
    } as Record<string, string>)[key] ?? key,
  }),
}));

import { ColorPreviewConfirm } from "./ColorPreviewConfirm";

describe("ColorPreviewConfirm", () => {
  afterEach(cleanup);

  it("keeps save and discard visible in a bottom viewport tray", async () => {
    const onSave = vi.fn();
    const onDiscard = vi.fn();
    render(
      <ColorPreviewConfirm
        seconds={12}
        saving={false}
        onSave={onSave}
        onDiscard={onDiscard}
      />,
    );

    const tray = screen.getByRole("status");
    expect(tray.style.position).toBe("fixed");
    expect(tray.style.bottom).not.toBe("");
    expect(screen.getByText("Se desharán en 12s")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await Promise.resolve();
    fireEvent.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(onSave).toHaveBeenCalledOnce();
    expect(onDiscard).toHaveBeenCalledOnce();
  });

  it("prevents duplicate actions while the save is pending", () => {
    render(
      <ColorPreviewConfirm
        seconds={8}
        saving
        onSave={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Guardando…" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "Deshacer" }).getAttribute("aria-disabled")).toBe("true");
  });
});
