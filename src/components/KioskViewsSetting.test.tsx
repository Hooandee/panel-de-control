// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const kiosk = { supported: true };
const chosen: string[] = [];
const setKioskViewChosen = vi.fn((id: string) => chosen.push(id));

vi.mock("@decky/ui", () => ({
  ToggleField: ({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) => (
    <button type="button" aria-pressed={checked} onClick={onChange}>{label}</button>
  ),
}));
vi.mock("../api", () => ({ getKioskState: async () => ({ ...kiosk }) }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../customize/viewStore", () => ({
  useViews: () => [
    { id: "a", name: "Juego", icon: "star", blocks: ["tdp"] },
    { id: "b", name: "Vacía", icon: "star", blocks: [] },
  ],
}));
vi.mock("../customize/kioskViewStore", () => ({
  useKioskViewIds: () => chosen,
  setKioskViewChosen: (id: string) => setKioskViewChosen(id),
}));

import { KioskViewsSetting } from "./KioskViewsSetting";

afterEach(cleanup);
beforeEach(() => {
  kiosk.supported = true;
  chosen.length = 0;
  setKioskViewChosen.mockClear();
});

describe("KioskViewsSetting", () => {
  it("lists only views with blocks and toggles them", async () => {
    render(<KioskViewsSetting />);
    await waitFor(() => expect(screen.getByText("customize.kiosk.title")).toBeTruthy());
    expect(screen.queryByText("Vacía")).toBeNull();
    fireEvent.click(screen.getByText("Juego"));
    expect(setKioskViewChosen).toHaveBeenCalledWith("a");
  });

  it("stays hidden on machines without a second screen", async () => {
    kiosk.supported = false;
    const { container } = render(<KioskViewsSetting />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container.textContent).toBe("");
  });
});
