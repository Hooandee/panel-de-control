// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const context = vi.hoisted(() => ({
  monitorOnly: false,
  desktop: false,
  visiblePowerBlocks: ["desktopPower"],
}));

vi.mock("../customize/blocks", () => ({
  BLOCK_GAP: 6,
  Block: ({ id }: { id: string }) => <div>{`block:${id}`}</div>,
  SectionView: ({ sectionId, desktopMode }: { sectionId: string; desktopMode?: boolean }) => (
    <div>{`section:${sectionId}:${desktopMode ? "desktop" : "handheld"}`}</div>
  ),
  useSectionBlockIds: () => ({
    ids: context.visiblePowerBlocks,
    visible: context.visiblePowerBlocks,
  }),
}));

vi.mock("../tdp/potenciaContext", () => ({
  usePotencia: () => ({ monitorOnly: context.monitorOnly }),
}));

vi.mock("../desktop/useDesktop", () => ({
  useDesktopState: () => ({ state: { enabled: context.desktop } }),
}));

vi.mock("../desktop/presentation", () => ({
  desktopUiActive: (state: { enabled?: boolean } | null) => !!state?.enabled,
}));

vi.mock("./providerMounts", () => ({
  PotenciaProviderMount: ({
    children,
    showProfileSelector,
  }: {
    children: ReactNode;
    showProfileSelector?: boolean;
  }) => (
    <>
      {showProfileSelector && <div>profile-selector</div>}
      {children}
    </>
  ),
}));

import { PotenciaSection } from "./PotenciaSection";

describe("PotenciaSection independent blocks", () => {
  afterEach(() => {
    context.monitorOnly = false;
    context.desktop = false;
    context.visiblePowerBlocks = ["desktopPower"];
    cleanup();
  });

  it("keeps independent Steam blocks visible while PDC TDP is monitor-only", () => {
    context.monitorOnly = true;

    render(<PotenciaSection />);

    expect(screen.getByText("block:tdp")).toBeTruthy();
    expect(screen.getByText("section:power:handheld")).toBeTruthy();
    expect(screen.getByText("profile-selector")).toBeTruthy();
  });

  it("uses the desktop power layout without duplicating the handheld TDP core", () => {
    context.desktop = true;

    render(<PotenciaSection />);

    expect(screen.getByText("section:power:desktop")).toBeTruthy();
    expect(screen.queryByText("block:tdp")).toBeNull();
    expect(screen.queryByText("profile-selector")).toBeNull();
  });

  it("keeps the profile selector in desktop mode when Steam controls are visible", () => {
    context.desktop = true;
    context.visiblePowerBlocks = ["desktopPower", "steamPerformance"];

    render(<PotenciaSection />);

    expect(screen.getByText("profile-selector")).toBeTruthy();
  });
});
