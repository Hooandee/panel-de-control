// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));

import type { DeviceInfo } from "../api";
import { DeviceHeader } from "./DeviceHeader";

const device: DeviceInfo = {
  key: "test-device",
  display_name: "Test Device",
  chip: "Test APU",
  vendor: "amd",
  tdp_min: 5,
  tdp_default: 15,
  tdp_max: 30,
  tdp_max_charger: 30,
  is_generic: false,
  experimental: false,
  cooler_max: null,
  experimental_tdp_max_ac: null,
  gpu_gen: "rdna3",
  charger_only_extra: false,
};

describe("DeviceHeader", () => {
  beforeEach(() => window.localStorage.setItem("panel-de-control-lang", "es"));
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it.each([
    [{ ...device, is_generic: true }, /Dispositivo no reconocido/],
    [{ ...device, experimental: true }, /Modelo reconocido/],
  ] as const)("exposes an accessible status for an unvalidated device", (unvalidated, label) => {
    render(<DeviceHeader device={unvalidated} />);

    expect(screen.getByRole("img", { name: label })).toBeTruthy();
  });
});
