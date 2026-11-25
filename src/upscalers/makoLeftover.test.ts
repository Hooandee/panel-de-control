import { expect, it, vi } from "vitest";

vi.mock("../api", () => ({ getUpscalerLaunchReceipt: vi.fn() }));
vi.mock("../launch/steamApi", () => ({ readAppDetails: vi.fn(), writeLaunchOptions: vi.fn() }));
vi.mock("../system/uiEvents", () => ({ recordUiEvent: vi.fn() }));

import { hasMakoLeftover, withoutMako } from "./makoLeftover";

it("takes another tool's Mako out of the launch options and keeps the rest", () => {
  expect(withoutMako("MANGOHUD=1 MAKO_PROFILE=mako ~/.local/bin/mako-run --fps=60 gamemoderun %command% -dx11"))
    .toBe("MANGOHUD=1 gamemoderun %command% -dx11");
  expect(withoutMako("~/.local/bin/mako-run %command%")).toBe("");
});

it("leaves launch options without Mako, or too odd to edit, alone", () => {
  expect(withoutMako("gamemoderun %command%")).toBeNull();
  expect(withoutMako("%command% %command%")).toBeNull();
});

it("only counts Mako that Panel did not add as a leftover", () => {
  const ours = { version: 1 as const, env: [], wrappers: { before: [], applied: ["/x/bin/mako-launch"], added: ["/x/bin/mako-launch"] } };
  expect(hasMakoLeftover("/x/bin/mako-launch %command%", ours)).toBe(false);
  expect(hasMakoLeftover("~/.local/bin/mako-run %command%", null)).toBe(true);
  expect(hasMakoLeftover("%command%", null)).toBe(false);
});
