import { describe, expect, it } from "vitest";

import { effectiveAutoRange, resolveAutoView } from "./autoView";

const globalConfig = { enabled: false, target_fps: 40, initial_tdp: 15, min_tdp: null, max_tdp: null };
const gameConfig = { enabled: true, target_fps: 60, initial_tdp: 22, min_tdp: null, max_tdp: null };
const livePower = {
  auto_tdp: true,
  setpoint: 20,
} as never;

describe("AutoTDP scope presentation", () => {
  it("restores the requested range when charger capacity becomes available", () => {
    const config = { ...gameConfig, min_tdp: 10, max_tdp: 40 };
    const limits = { min: 5, default: 15, max: 25, max_ac: 40 };
    expect(effectiveAutoRange(config, limits, false)).toEqual({ min: 10, max: 25 });
    expect(effectiveAutoRange(config, limits, true)).toEqual({ min: 10, max: 40 });
    expect(config).toMatchObject({ min_tdp: 10, max_tdp: 40 });
  });

  it("clamps both selected endpoints up to a temporary firmware minimum", () => {
    const config = { ...gameConfig, min_tdp: 5, max_tdp: 10 };
    expect(effectiveAutoRange(config, { min: 15, default: 15, max: 25, max_ac: 40 }, false)).toEqual({ min: 15, max: 15 });
    expect(config).toMatchObject({ min_tdp: 5, max_tdp: 10 });
  });

  it.each([
    { minimum: null, maximum: null, expected: 15 },
    { minimum: 20, maximum: 30, expected: 20 },
    { minimum: 5, maximum: 10, expected: 10 },
    { minimum: 30, maximum: 40, expected: 25 },
  ])("shows the responsive grid floor for $minimum–$maximum W", ({ minimum, maximum, expected }) => {
    const config = { ...globalConfig, enabled: true, initial_tdp: 8, min_tdp: minimum, max_tdp: maximum };
    const view = resolveAutoView({
      follows_global: true,
      global_auto_config: config,
      auto_config: config,
      auto_limits: { min: 5, default: 12, max: 25, max_ac: 35 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      on_ac: false,
    }, livePower, "global", false);
    expect(view.power?.setpoint).toBe(expected);
    expect(view.config.max_tdp).toBe(maximum);
  });

  it("shows global as off while a game-owned AutoTDP is running", () => {
    const view = resolveAutoView({
      auto_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      on_ac: false,
      follows_global: false,
      global_auto_config: globalConfig,
      auto_config: gameConfig,
    }, livePower, "global", true);

    expect(view.config).toEqual(globalConfig);
    expect(view.liveApplies).toBe(false);
    expect(view.power?.auto_tdp).toBe(false);
    expect(view.power?.setpoint).toBe(20);
    expect(view.hideManualSuggestion).toBe(true);
  });

  it("shows the owned game config and its live state together", () => {
    const view = resolveAutoView({
      auto_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      on_ac: false,
      follows_global: false,
      global_auto_config: globalConfig,
      auto_config: gameConfig,
    }, livePower, "game", true);

    expect(view.config).toEqual(gameConfig);
    expect(view.liveApplies).toBe(true);
    expect(view.power?.auto_tdp).toBe(true);
    expect(view.power?.setpoint).toBe(20);
    expect(view.hideManualSuggestion).toBe(true);
  });

  it("preserves manual suggestions when Auto is off for the running game", () => {
    const view = resolveAutoView({
      follows_global: true, auto_config: globalConfig, global_auto_config: globalConfig,
      auto_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 }, on_ac: false,
    }, { setpoint: 20, auto_tdp: false } as never, "global", true);
    expect(view.hideManualSuggestion).toBe(false);
    expect(view.power?.setpoint).toBe(20);
  });

  it("uses global live state when the current game follows global", () => {
    const enabledGlobal = { ...globalConfig, enabled: true, initial_tdp: 18 };
    const view = resolveAutoView({
      auto_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      on_ac: false,
      follows_global: true,
      global_auto_config: enabledGlobal,
      auto_config: enabledGlobal,
    }, livePower, "global", true);

    expect(view.liveApplies).toBe(true);
    expect(view.power?.auto_tdp).toBe(true);
    expect(view.power?.setpoint).toBe(20);
  });

  it("shows the selected initial TDP instead of another profile's live setpoint", () => {
    const enabledGlobal = { ...globalConfig, enabled: true, initial_tdp: 18 };
    const view = resolveAutoView({
      auto_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      on_ac: false,
      follows_global: false,
      global_auto_config: enabledGlobal,
      auto_config: gameConfig,
    }, livePower, "global", true);

    expect(view.liveApplies).toBe(false);
    expect(view.power?.auto_tdp).toBe(true);
    expect(view.power?.setpoint).toBe(18);
  });

  it("shows the TDP physically held while the menu is open", () => {
    const enabledGlobal = { ...globalConfig, enabled: true, initial_tdp: 8 };
    const view = resolveAutoView({
      auto_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
      on_ac: false,
      follows_global: true,
      global_auto_config: enabledGlobal,
      auto_config: enabledGlobal,
    }, {
      auto_tdp: true,
      setpoint: 8,
      auto: {
        state: "paused",
        reason: "ui_active",
        held_watts: 22,
      },
    } as never, "global", true);

    expect(view.power?.setpoint).toBe(22);
  });
});
