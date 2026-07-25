// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("@decky/ui", () => ({
  Focusable: ({
    children,
    noFocusRing: _noFocusRing,
    onActivate,
    onClick,
    ...props
  }: {
    children?: ReactNode;
    noFocusRing?: boolean;
    onActivate?: () => void;
  } & HTMLAttributes<HTMLDivElement>) => (
    <div {...props} onClick={onClick ?? onActivate}>{children}</div>
  ),
}));
vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => `copy:${key}`,
  }),
}));

import { TdpConflictCard } from "./TdpConflictCard";

const noop = () => {};
const legacyDescription = "copy:tdp.conflict.card.desc";
const powerstationDescription = "copy:tdp.conflict.card.desc.powerstation";

describe("TdpConflictCard conflict explanation", () => {
  afterEach(cleanup);

  it.each([
    {
      rival: "SimpleDeckyTDP",
      rivals: { sdtdp: true, hhd: false, powerstation: false },
    },
    {
      rival: "HHD",
      rivals: { sdtdp: false, hhd: true, powerstation: false },
    },
  ])("preserves the existing takeover explanation for $rival", ({ rivals }) => {
    render(
      <TdpConflictCard
        rivals={rivals}
        onDisableSdtdp={noop}
        onTakeHhd={noop}
        onDisablePdcTdp={noop}
      />,
    );

    expect(screen.getByText(legacyDescription)).toBeTruthy();
    expect(screen.queryByText(powerstationDescription)).toBeNull();
  });

  it("uses the neutral explanation when PowerStation is active", () => {
    render(
      <TdpConflictCard
        rivals={{ sdtdp: false, hhd: false, powerstation: true }}
        onDisableSdtdp={noop}
        onTakeHhd={noop}
        onDisablePdcTdp={noop}
      />,
    );

    expect(screen.getByText(powerstationDescription)).toBeTruthy();
    expect(screen.queryByText(legacyDescription)).toBeNull();
    expect(
      screen.getByText("copy:tdp.conflict.powerstation.disablePdc"),
    ).toBeTruthy();
  });

  it("keeps the neutral explanation when PowerStation coexists with another rival", () => {
    render(
      <TdpConflictCard
        rivals={{ sdtdp: true, hhd: true, powerstation: true }}
        onDisableSdtdp={noop}
        onTakeHhd={noop}
        onDisablePdcTdp={noop}
      />,
    );

    expect(screen.getByText(powerstationDescription)).toBeTruthy();
    expect(screen.queryByText(legacyDescription)).toBeNull();
  });
});
