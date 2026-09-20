// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

import { ProfileSelector } from "./ProfileSelector";

describe("ProfileSelector", () => {
  afterEach(cleanup);

  it("uses the generic game scope label instead of the full title", () => {
    render(
      <ProfileSelector
        scope="game"
        gameName="Sekiro™: Shadows Die Twice - Edición del año"
        hasGameProfile
        globalLabel="Global"
        inheritHint="Inherited"
        onScope={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.scope.game")).toBeTruthy();
    expect(screen.queryByText(/Sekiro/)).toBeNull();
  });
});
