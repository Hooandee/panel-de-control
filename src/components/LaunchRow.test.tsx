// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate: _onActivate, ...props }: { children: ReactNode; onActivate?: () => void; [key: string]: unknown }) => (
    <div {...props}>{children}</div>
  ),
  TextField: () => null,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { CATALOG, type LaunchTools } from "../launch/catalog";
import type { LaunchEditor } from "../launch/useLaunchEditor";
import { LaunchRow } from "./LaunchRow";

const gamemode = CATALOG.find((pill) => pill.id === "gamemode")!;
const tools = { gamemode: true } as LaunchTools;
const editor = { selections: {}, set: vi.fn() } as unknown as LaunchEditor;

describe("LaunchRow", () => {
  afterEach(cleanup);

  it("keeps the toggle beside its title in a row the gamepad crosses with right", () => {
    render(<LaunchRow pill={gamemode} ed={editor} tools={tools} gpu="rdna2" supportedEnvs={[]} catalog={CATALOG} />);

    const toggle = screen.getByRole("switch", { name: "params.pill.gamemode" });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(toggle.closest("[flow-children]")?.getAttribute("flow-children")).toBe("row");
  });
});
