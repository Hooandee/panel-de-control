// @vitest-environment happy-dom
import { ReactNode } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const store = vi.hoisted(() => ({
  entries: [{ catalogId: "hooandee-bubble", summary: "6 páginas", updatedAt: 1_700_000_000, bytes: 3000 }],
}));

vi.mock("@decky/ui", () => ({
  ButtonItem: ({ children, disabled, onClick }: { children: ReactNode; disabled?: boolean; onClick(): void }) => (
    <button disabled={disabled} onClick={onClick}>{children}</button>
  ),
}));

vi.mock("../themes/themeDataClient", () => ({
  listThemeData: async () => store.entries,
  resetThemeData: async (catalogId: string) => {
    store.entries = store.entries.filter((entry) => entry.catalogId !== catalogId);
    return true;
  },
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key, lang: "es" }),
}));

import { ThemeDataCard } from "./ThemeDataCard";

afterEach(cleanup);

describe("ThemeDataCard", () => {
  it("keeps a reset theme's row, marked as reset, so focus has somewhere to stay", async () => {
    render(<ThemeDataCard names={{ "hooandee-bubble": "Bubble" }} />);
    const button = await screen.findByRole("button", { name: "themes.data.reset" });

    fireEvent.click(button);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "themes.data.confirm" }));
    });

    const done = await screen.findByRole("button", { name: "themes.data.cleared" });
    expect(done.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Bubble")).toBeTruthy();
  });
});
