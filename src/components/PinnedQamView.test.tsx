// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  ErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("../i18n", () => ({
  I18nProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("./QamPanelGate", () => ({
  QamPanelGate: ({ children, surfaceId }: { children: ReactNode; surfaceId: string }) => (
    <div data-testid="pinned-gate" data-surface-id={surfaceId}>{children}</div>
  ),
}));

vi.mock("./ControlCenter", () => ({
  ControlCenter: ({ target }: { target?: { kind: string; id?: string } }) => (
    <div data-testid="targeted-control-center" data-kind={target?.kind} data-id={target?.id} />
  ),
}));

import { PinnedQamView } from "./PinnedQamView";

describe("PinnedQamView", () => {
  afterEach(cleanup);

  it("passes the direct section as the entry destination", () => {
    render(
      <PinnedQamView
        token="pdc:section:hud"
        target={{ kind: "section", id: "hud" }}
        lifecycle={new AbortController().signal}
      />,
    );

    expect(screen.getByTestId("pinned-gate").dataset.surfaceId).toBe("pdc:section:hud");
    expect(screen.getByTestId("targeted-control-center").dataset).toMatchObject({
      kind: "section",
      id: "hud",
    });
  });

  it("passes Inicio as the entry destination", () => {
    render(
      <PinnedQamView
        token="pdc:home"
        target={{ kind: "home" }}
        lifecycle={new AbortController().signal}
      />,
    );

    expect(screen.getByTestId("targeted-control-center").dataset.kind).toBe("home");
  });
});
