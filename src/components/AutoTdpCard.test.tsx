// @vitest-environment happy-dom
import type { ComponentProps } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => ({
  toggle: null as Record<string, any> | null,
  sliders: {} as Record<string, Record<string, any>>,
}));

vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: any) => <div>{children}</div>,
  SliderField: (props: Record<string, any>) => {
    captured.sliders[String(props.label)] = props;
    return <div>{props.label}</div>;
  },
  ToggleField: (props: Record<string, any>) => {
    captured.toggle = props;
    return <div>{props.label}{props.description}</div>;
  },
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${Object.values(vars).join(" ")}` : key,
  }),
}));

import { AutoTdpCard } from "./AutoTdpCard";

type Props = ComponentProps<typeof AutoTdpCard>;

const config: Props["config"] = {
  enabled: true,
  target_fps: 40,
  initial_tdp: 16,
  min_tdp: null,
  max_tdp: null,
};
const live: NonNullable<Props["live"]> = {
  state: "holding",
  reason: "cooldown",
  setpoint: 14,
  fps: 40.2,
  target_fps: 40,
  signal_age_s: 0.2,
  focus: "42",
  seed_source: "initial",
  seed_watts: 16,
  held_watts: null,
};

function renderCard(overrides: Partial<Props> = {}) {
  const props: Props = {
    config,
    scope: "game",
    limits: { min: 5, default: 15, max: 35, max_ac: 35 },
    requestLimits: { min: 3, default: 15, max: 35, max_ac: 40 },
    onAc: true,
    maxTargetFps: 60,
    live,
    liveApplies: true,
    onToggle: vi.fn(),
    onTargetFps: vi.fn(),
    onInitialTdp: vi.fn(),
    onMinTdp: vi.fn(),
    onMaxTdp: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<AutoTdpCard {...props} />) };
}

describe("AutoTdpCard", () => {
  afterEach(() => {
    cleanup();
    captured.toggle = null;
    for (const label of Object.keys(captured.sliders)) delete captured.sliders[label];
  });

  it("uses the selected disabled scope instead of unrelated live state", () => {
    renderCard({
      config: { ...config, enabled: false },
      scope: "global",
      live: { ...live, state: "recovering" },
      liveApplies: false,
    });

    expect(captured.toggle?.checked).toBe(false);
    expect(captured.sliders).toEqual({});
    expect(screen.getByText("tdp.auto.experimental")).toBeTruthy();
    expect(screen.getByText("tdp.auto.scope.global")).toBeTruthy();
    expect(screen.queryByText(/tdp\.auto\.status\.recovering/)).toBeNull();
  });

  it.each([
    [57, 60, 60],
    [72, undefined, 240],
  ])("allows target %i FPS up to the detected ceiling", (targetFps, maxTargetFps, expectedMax) => {
    const onTargetFps = vi.fn();
    renderCard({
      config: { ...config, target_fps: targetFps },
      maxTargetFps,
      onTargetFps,
    });

    const target = captured.sliders["tdp.auto.target.label"];
    expect(target).toMatchObject({
      value: targetFps,
      min: 20,
      max: expectedMax,
      step: 1,
      editableValue: true,
      minimumDpadGranularity: 1,
      valueSuffix: " FPS",
    });
    target.onChange(targetFps + 1);
    expect(onTargetFps).toHaveBeenCalledWith(targetFps + 1);
  });

  it("keeps the requested range while clamping the live battery start", () => {
    renderCard({
      config: { ...config, min_tdp: 10, max_tdp: 40, initial_tdp: 35 },
      limits: { min: 5, default: 15, max: 25, max_ac: 40 },
      requestLimits: { min: 5, default: 15, max: 35, max_ac: 40 },
      onAc: false,
      live: null,
      liveApplies: false,
    });

    expect(captured.sliders["tdp.auto.range.min"]).toMatchObject({ value: 10, min: 5, max: 40 });
    expect(captured.sliders["tdp.auto.range.max"]).toMatchObject({ value: 40, min: 5, max: 40 });
    expect(captured.sliders["tdp.auto.initial.label"]).toMatchObject({ value: 25, min: 10, max: 25 });
    expect(screen.getByText("tdp.auto.range.constrained 10 25")).toBeTruthy();
  });

  it("exposes game scope controls and forwards direct edits", () => {
    const onTargetFps = vi.fn();
    const onInitialTdp = vi.fn();
    renderCard({
      config: { ...config, target_fps: 45, initial_tdp: 18 },
      limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      requestLimits: { min: 5, default: 15, max: 35, max_ac: 40 },
      onTargetFps,
      onInitialTdp,
    });

    expect(screen.getByText("tdp.scope.game")).toBeTruthy();
    expect(captured.sliders["tdp.auto.target.label"].value).toBe(45);
    expect(captured.sliders["tdp.auto.initial.label"]).toMatchObject({
      value: 18,
      min: 5,
      max: 40,
      valueSuffix: " W",
      className: "pdc-contained-slider",
    });
    expect(screen.queryByText(/tdp\.auto\.range\.constrained/)).toBeNull();

    captured.sliders["tdp.auto.target.label"].onChange(57);
    captured.sliders["tdp.auto.initial.label"].onChange(22);
    expect(onTargetFps).toHaveBeenCalledWith(57);
    expect(onInitialTdp).toHaveBeenCalledWith(22);
  });

  it.each([
    ["initial", 40, false],
    ["learned", 40, true],
    ["learned", 60, false],
  ] as const)(
    "shows learned origin only for a matching learned seed (%s, %i FPS)",
    (seedSource, selectedFps, expected) => {
      renderCard({
        config: { ...config, target_fps: selectedFps },
        live: { ...live, seed_source: seedSource, seed_watts: 11, target_fps: 40 },
      });

      expect(screen.queryByText("tdp.auto.learned_start 11 40") !== null).toBe(expected);
    },
  );

  it.each([
    ["holding", "above_target", 14, null, 40.2, "tdp.auto.status.holding 40 14"],
    ["paused", "no_game_focus", 5, 19, null, "tdp.auto.status.paused_menu 19"],
    ["paused", "ui_active", 5, null, null, "tdp.auto.status.paused_menu_stable"],
    ["warming", "warming", 16, null, null, "tdp.auto.status.warming 16"],
    ["paused", "fps_stale", 16, null, null, "tdp.auto.status.paused_signal 16"],
    ["paused", "focus_mismatch", 15, null, null, "tdp.auto.status.paused 15"],
  ] as const)(
    "maps %s/%s to its user-facing status",
    (state, reason, setpoint, heldWatts, fps, expected) => {
      renderCard({
        live: { ...live, state, reason, setpoint, held_watts: heldWatts, fps },
      });

      expect(screen.getByText(expected)).toBeTruthy();
    },
  );
});
