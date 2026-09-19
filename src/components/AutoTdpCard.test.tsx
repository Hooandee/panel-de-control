// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => ({
  toggle: null as Record<string, any> | null,
  dropdown: null as Record<string, any> | null,
  sliders: {} as Record<string, Record<string, any>>,
}));

vi.mock("@decky/ui", () => ({
  DropdownItem: (props: Record<string, any>) => {
    captured.dropdown = props;
    return <div>{props.label}</div>;
  },
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

const config = { enabled: false, target_fps: 40, initial_tdp: 16, min_tdp: null, max_tdp: null };
const live = {
  state: "holding" as const,
  reason: "cooldown",
  setpoint: 14,
  fps: 40.2,
  target_fps: 40,
  signal_age_s: 0.2,
  focus: "42",
  seed_source: "initial" as const,
  seed_watts: 16,
  held_watts: null,
};

describe("AutoTdpCard", () => {
  afterEach(() => {
    cleanup();
    captured.toggle = null;
    captured.dropdown = null;
    for (const label of Object.keys(captured.sliders)) delete captured.sliders[label];
  });

  it("uses the selected scope config instead of the unrelated live toggle", () => {
    render(
      <AutoTdpCard
        config={config}
        scope="global"
        limits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={{ ...live, state: "recovering" }}
        liveApplies={false}
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(captured.toggle?.checked).toBe(false);
    expect(captured.dropdown).toBeNull();
    expect(captured.sliders).toEqual({});
    expect(screen.getByText("tdp.auto.scope.global")).toBeTruthy();
    expect(screen.queryByText(/tdp\.auto\.status\.recovering/)).toBeNull();
  });

  it("keeps the experimental status visible on the automatic controls", () => {
    render(
      <AutoTdpCard
        config={config}
        scope="global"
        limits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={null}
        liveApplies={false}
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.experimental")).toBeTruthy();
  });

  it("allows any whole FPS target with direct editing and one-step controller input", () => {
    const onTargetFps = vi.fn();
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true, target_fps: 57 }}
        scope="global"
        limits={{ min: 3, default: 12, max: 15, max_ac: 15 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        maxTargetFps={60}
        live={null}
        liveApplies={false}
        onToggle={vi.fn()}
        onTargetFps={onTargetFps}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    const target = captured.sliders["tdp.auto.target.label"];
    expect(captured.dropdown).toBeNull();
    expect(target).toMatchObject({
      value: 57,
      min: 20,
      max: 60,
      step: 1,
      showValue: true,
      editableValue: true,
      validValues: "steps",
      minimumDpadGranularity: 1,
      valueSuffix: " FPS",
      className: "pdc-contained-slider",
    });

    target.onChange(58);
    expect(onTargetFps).toHaveBeenCalledWith(58);
  });

  it("offers the full safe range when the panel refresh is unknown", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true, target_fps: 72 }}
        scope="global"
        limits={{ min: 3, default: 12, max: 15, max_ac: 15 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={null}
        liveApplies={false}
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(captured.sliders["tdp.auto.target.label"]).toMatchObject({
      value: 72,
      min: 20,
      max: 240,
    });
  });

  it("uses the actual controller state for obsolete presentation reasons", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true, target_fps: 40 }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        maxTargetFps={60}
        live={{ ...live, reason: "above_target", fps: 60 }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.status.holding 60 14")).toBeTruthy();
    expect(screen.queryByText(/tdp\.auto\.status\.above_target/)).toBeNull();
  });

  it("keeps the editable range durable and explains a temporary battery ceiling", () => {
    render(<AutoTdpCard
      config={{ ...config, enabled: true, min_tdp: 10, max_tdp: 40, initial_tdp: 35 }}
      scope="game"
      limits={{ min: 5, default: 15, max: 25, max_ac: 40 }}
      requestLimits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
      onAc={false} live={null} liveApplies={false}
      onToggle={vi.fn()} onTargetFps={vi.fn()} onInitialTdp={vi.fn()}
      onMinTdp={vi.fn()} onMaxTdp={vi.fn()}
    />);
    expect(captured.sliders["tdp.auto.range.min"]).toMatchObject({ value: 10, min: 5, max: 40, step: 1, editableValue: true });
    expect(captured.sliders["tdp.auto.range.max"]).toMatchObject({ value: 40, min: 5, max: 40, step: 1, editableValue: true });
    expect(captured.sliders["tdp.auto.initial.label"]).toMatchObject({ value: 25, min: 10, max: 25, editableValue: true });
    expect(screen.getByText("tdp.auto.range.constrained 10 25")).toBeTruthy();
  });

  it("does not show a firmware note when the selected range is available", () => {
    render(<AutoTdpCard
      config={{ ...config, enabled: true, min_tdp: 10, max_tdp: 20 }}
      scope="game" limits={{ min: 5, default: 15, max: 25, max_ac: 40 }}
      requestLimits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
      onAc={false} live={null} liveApplies={false}
      onToggle={vi.fn()} onTargetFps={vi.fn()} onInitialTdp={vi.fn()}
      onMinTdp={vi.fn()} onMaxTdp={vi.fn()}
    />);
    expect(captured.sliders["tdp.auto.initial.label"]).toMatchObject({ min: 10, max: 20 });
    expect(screen.queryByText(/tdp\.auto\.range\.constrained/)).toBeNull();
  });

  it("mentions learned memory only when it supplied the starting TDP", () => {
    const { rerender } = render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        maxTargetFps={60}
        live={{ ...live, seed_source: "initial" }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );
    expect(screen.queryByText("tdp.auto.learned_start")).toBeNull();

    rerender(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        maxTargetFps={60}
        live={{ ...live, seed_source: "learned", seed_watts: 11 }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );
    expect(screen.getByText("tdp.auto.learned_start 11 40")).toBeTruthy();
  });

  it("does not attribute a previous session's learned start to a newly selected FPS target", () => {
    render(<AutoTdpCard
      config={{ ...config, enabled: true, target_fps: 60 }} scope="game"
      limits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
      requestLimits={{ min: 5, default: 15, max: 35, max_ac: 40 }} onAc
      live={{ ...live, seed_source: "learned", seed_watts: 11, target_fps: 40 }} liveApplies
      onToggle={vi.fn()} onTargetFps={vi.fn()} onInitialTdp={vi.fn()}
      onMinTdp={vi.fn()} onMaxTdp={vi.fn()}
    />);
    expect(screen.queryByText(/tdp\.auto\.learned_start/)).toBeNull();
  });

  it("keeps unknown pause reasons generic instead of labelling them as a menu", () => {
    render(<AutoTdpCard
      config={{ ...config, enabled: true }} scope="game"
      limits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
      requestLimits={{ min: 5, default: 15, max: 35, max_ac: 40 }} onAc
      live={{ ...live, state: "paused", reason: "focus_mismatch", held_watts: 15 }} liveApplies
      onToggle={vi.fn()} onTargetFps={vi.fn()} onInitialTdp={vi.fn()}
      onMinTdp={vi.fn()} onMaxTdp={vi.fn()}
    />);
    expect(screen.getByText("tdp.auto.status.paused 15")).toBeTruthy();
    expect(screen.queryByText(/tdp\.auto\.status\.paused_menu/)).toBeNull();
  });

  it("makes game scope, FPS target and initial TDP explicit", () => {
    const onTargetFps = vi.fn();
    const onInitialTdp = vi.fn();
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true, target_fps: 45, initial_tdp: 18 }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 40 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={live}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={onTargetFps}
        onInitialTdp={onInitialTdp}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.scope.game")).toBeTruthy();
    expect(screen.queryByText(/Dolphin/)).toBeNull();
    expect(captured.sliders["tdp.auto.target.label"]).toMatchObject({
      label: "tdp.auto.target.label",
      value: 45,
    });
    expect(captured.sliders["tdp.auto.initial.label"]).toMatchObject({
      label: "tdp.auto.initial.label",
      value: 18,
      min: 5,
      max: 40,
      step: 1,
      valueSuffix: " W",
      className: "pdc-contained-slider",
    });

    captured.sliders["tdp.auto.target.label"].onChange(57);
    captured.sliders["tdp.auto.initial.label"].onChange(22);
    expect(onTargetFps).toHaveBeenCalledWith(57);
    expect(onInitialTdp).toHaveBeenCalledWith(22);
  });

  it("keeps the initial TDP inside the currently available battery range", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true, initial_tdp: 30 }}
        scope="global"
        limits={{ min: 8, default: 15, max: 25, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc={false}
        live={null}
        liveApplies={false}
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(captured.sliders["tdp.auto.initial.label"]).toMatchObject({
      value: 25,
      min: 8,
      max: 25,
    });
    expect(screen.getByText("tdp.auto.status.waiting_game")).toBeTruthy();
  });

  it("summarizes live FPS and TDP in one human status line", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={live}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.status.holding 40 14")).toBeTruthy();
  });

  it("explains a menu pause without presenting AutoTDP as broken", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={{ ...live, state: "paused", reason: "no_game_focus", fps: null }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText(/tdp\.auto\.status\.paused_menu/)).toBeTruthy();
    expect(screen.queryByText(/error|broken|roto/i)).toBeNull();
  });

  it("explains an explicit Steam overlay pause as a menu", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={{ ...live, state: "paused", reason: "ui_active", setpoint: 5, held_watts: 19, fps: null }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.status.paused_menu 19")).toBeTruthy();
    expect(screen.queryByText("tdp.auto.status.paused_menu 5")).toBeNull();
  });

  it("uses a neutral menu status when physical readback is unavailable", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="game"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={{ ...live, state: "paused", reason: "ui_active", setpoint: 5, held_watts: null, fps: null }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.status.paused_menu_stable")).toBeTruthy();
    expect(screen.queryByText(/paused_menu 5/)).toBeNull();
  });

  it("includes the maintained TDP while AutoTDP is preparing", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="global"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={{ ...live, state: "warming", reason: "warming", setpoint: 16, fps: null }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.status.warming 16")).toBeTruthy();
  });

  it("includes the maintained TDP while waiting for a reliable FPS signal", () => {
    render(
      <AutoTdpCard
        config={{ ...config, enabled: true }}
        scope="global"
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        requestLimits={{ min: 3, default: 15, max: 35, max_ac: 40 }}
        onAc
        live={{ ...live, state: "paused", reason: "fps_stale", setpoint: 16, fps: null }}
        liveApplies
        onToggle={vi.fn()}
        onTargetFps={vi.fn()}
        onInitialTdp={vi.fn()}
        onMinTdp={vi.fn()}
        onMaxTdp={vi.fn()}
      />,
    );

    expect(screen.getByText("tdp.auto.status.paused_signal 16")).toBeTruthy();
  });
});
