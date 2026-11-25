// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("@decky/ui", () => ({ Focusable: "button", TextField: "input" }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
import { UnavailableFsrRow } from "./LaunchRow";

afterEach(cleanup);
describe("Unavailable FSR row", () => {
  it("explains the state without an editable control or arbitrary launch variable", () => {
    const { container } = render(<UnavailableFsrRow reason="Proton not found" />);
    const control = screen.getByRole("switch");
    expect(control.getAttribute("aria-disabled")).toBe("true");
    expect(control.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("Proton not found")).toBeTruthy();
    expect(container.textContent).not.toContain("UPGRADE");
    expect(container.querySelector("button,input")).toBeNull();
    fireEvent.click(control);
    expect(control.getAttribute("aria-checked")).toBe("false");
  });
});
