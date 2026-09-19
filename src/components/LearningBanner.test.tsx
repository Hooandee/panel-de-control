// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("../customize/modules", () => ({ useModules: () => new Set<string>() }));

import { LearningBanner } from "./LearningBanner";

describe("LearningBanner", () => {
  afterEach(cleanup);

  it("renders the active label and game name as separate content", () => {
    render(
      <LearningBanner
        gameName="Sekiro™: Shadows Die Twice - Edición del año"
        status={{ telemetry_enabled: true, tdp_supported: true, fan_supported: true }}
        onOpenSettings={vi.fn()}
      />,
    );

    expect(screen.getByText("learning.active")).toBeTruthy();
    expect(screen.getByText("Sekiro™: Shadows Die Twice - Edición del año")).toBeTruthy();
    expect(screen.queryByText("learning.title")).toBeNull();
  });
});
