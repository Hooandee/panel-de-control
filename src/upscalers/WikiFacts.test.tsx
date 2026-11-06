// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("@decky/ui", () => ({ Navigation: {} }));
vi.mock("../api", () => ({ setUpscalerIni: vi.fn() }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../theme", () => ({ theme: { card: {}, space: { sm: 8, md: 12 } } }));
vi.mock("./parts", () => ({ ActionButton: ({ label }: any) => <button>{label}</button>, Note: ({ children }: any) => <div>{children}</div>, Row: ({ children }: any) => <div>{children}</div> }));
import { WikiFacts } from "./WikiFacts";
import type { RecipeInfo } from "./types";
afterEach(cleanup);
it("does not display a positive community verdict or internal input and patcher details", () => {
  const info = { status: "works", inputs: ["DLSS", "FSR2"], optipatcher: true, settings: { Foo: "true" }, page: "Game" } as unknown as RecipeInfo;
  const { container } = render(<WikiFacts appid="1" info={info} installed onApplied={() => {}} />);
  expect(container.textContent).toBe("");
});
it("keeps a compatibility limitation visible", () => {
  render(<WikiFacts appid="1" info={{ status: "partial" } as RecipeInfo} installed onApplied={() => {}} />);
  expect(screen.getByText("up.wiki.status.partial")).toBeTruthy();
});
it("keeps an actionable suggested setting for an installed game", () => {
  render(<WikiFacts appid="1" info={{ status: "works", suggestions: { Foo: "true" } } as unknown as RecipeInfo} installed onApplied={() => {}} />);
  expect(screen.getByRole("button", { name: "Foo=true" })).toBeTruthy();
});
