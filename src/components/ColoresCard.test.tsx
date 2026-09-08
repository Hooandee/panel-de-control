// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, style: _style, ...props }: { children?: ReactNode; onActivate?: () => void } & HTMLAttributes<HTMLDivElement>) => (
    <div data-focusable="true" onClick={onActivate} {...props}>{children}</div>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  showModal: vi.fn(),
}));

vi.mock("./ConfirmDialog", () => ({ ConfirmDialog: () => <div /> }));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => ({
    "system.rgb.title": "Iluminación RGB",
    "system.rgb.desc.installed": "Colores está instalado.",
    "system.rgb.open": "Abrir Colores",
  })[key] ?? key }),
}));

import { ColoresCard } from "./ColoresCard";

describe("ColoresCard", () => {
  afterEach(cleanup);

  it("exposes its bottom action as an explicit Decky focus target", () => {
    const onOpen = vi.fn();
    render(<ColoresCard state="open" onInstall={() => {}} onOpen={onOpen} onOpenStore={() => {}} />);

    const action = screen.getByTestId("system-rgb-action");
    const surface = screen.getByTestId("system-rgb-action-surface");
    expect(action.dataset.focusable).toBe("true");
    expect(surface.style.boxSizing).toBe("border-box");
    expect(surface.style.padding).toBe("12px 18px");
    expect(surface.style.width).toBe("100%");
    fireEvent.click(action);
    expect(onOpen).toHaveBeenCalledOnce();
  });
});
